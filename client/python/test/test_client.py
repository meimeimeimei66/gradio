import json
import os
import pathlib
import time
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from gradio_client import Client
from gradio_client.serializing import SimpleSerializable
from gradio_client.utils import Communicator, Status, StatusUpdate

os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

HF_TOKEN = "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"  # Intentionally revealing this key for testing purposes


class TestPredictionsFromSpaces:
    @pytest.mark.flaky
    def test_numerical_to_label_space(self):
        client = Client("gradio-tests/titanic-survival")
        output = client.predict("male", 77, 10, api_name="/predict").result()
        assert json.load(open(output))["label"] == "Perishes"
        with pytest.raises(
            ValueError,
            match="This Gradio app might have multiple endpoints. Please specify an `api_name` or `fn_index`",
        ):
            client.predict("male", 77, 10)
        with pytest.raises(
            ValueError,
            match="Cannot find a function with `api_name`: predict. Did you mean to use a leading slash?",
        ):
            client.predict("male", 77, 10, api_name="predict")

    @pytest.mark.flaky
    def test_private_space(self):
        client = Client("gradio-tests/not-actually-private-space", hf_token=HF_TOKEN)
        output = client.predict("abc", api_name="/predict").result()
        assert output == "abc"

    @pytest.mark.flaky
    def test_state(self):
        client = Client("gradio-tests/increment")
        output = client.predict(api_name="/increment_without_queue").result()
        assert output == 1
        output = client.predict(api_name="/increment_without_queue").result()
        assert output == 2
        output = client.predict(api_name="/increment_without_queue").result()
        assert output == 3
        client.reset_session()
        output = client.predict(api_name="/increment_without_queue").result()
        assert output == 1
        output = client.predict(api_name="/increment_with_queue").result()
        assert output == 2
        client.reset_session()
        output = client.predict(api_name="/increment_with_queue").result()
        assert output == 1
        output = client.predict(api_name="/increment_with_queue").result()
        assert output == 2

    @pytest.mark.flaky
    def test_job_status(self):
        statuses = []
        client = Client(src="gradio/calculator")
        job = client.predict(5, "add", 4)
        while not job.done():
            time.sleep(0.1)
            statuses.append(job.status())

        assert statuses
        # Messages are sorted by time
        assert sorted([s.time for s in statuses if s]) == [
            s.time for s in statuses if s
        ]
        assert sorted([s.code for s in statuses if s]) == [
            s.code for s in statuses if s
        ]

    @pytest.mark.flaky
    def test_job_status_queue_disabled(self):
        statuses = []
        client = Client(src="freddyaboulton/sentiment-classification")
        job = client.predict("I love the gradio python client", fn_index=0)
        while not job.done():
            time.sleep(0.02)
            statuses.append(job.status())
        statuses.append(job.status())
        assert all(s.code in [Status.PROCESSING, Status.FINISHED] for s in statuses)

    @pytest.mark.flaky
    def test_job_output_video(self):
        client = Client(src="gradio/video_component")
        job = client.predict(
            "https://huggingface.co/spaces/gradio/video_component/resolve/main/files/a.mp4",
            fn_index=0,
        )
        assert pathlib.Path(job.result()).exists()


class TestStatusUpdates:
    @patch("gradio_client.client.Endpoint.make_end_to_end_fn")
    def test_messages_passed_correctly(self, mock_make_end_to_end_fn):

        now = datetime.now()

        messages = [
            StatusUpdate(
                code=Status.STARTING,
                eta=None,
                rank=None,
                success=None,
                queue_size=None,
                time=now,
            ),
            StatusUpdate(
                code=Status.SENDING_DATA,
                eta=None,
                rank=None,
                success=None,
                queue_size=None,
                time=now + timedelta(seconds=1),
            ),
            StatusUpdate(
                code=Status.IN_QUEUE,
                eta=3,
                rank=2,
                queue_size=2,
                success=None,
                time=now + timedelta(seconds=2),
            ),
            StatusUpdate(
                code=Status.IN_QUEUE,
                eta=2,
                rank=1,
                queue_size=1,
                success=None,
                time=now + timedelta(seconds=3),
            ),
            StatusUpdate(
                code=Status.ITERATING,
                eta=None,
                rank=None,
                queue_size=None,
                success=None,
                time=now + timedelta(seconds=3),
            ),
            StatusUpdate(
                code=Status.FINISHED,
                eta=None,
                rank=None,
                queue_size=None,
                success=True,
                time=now + timedelta(seconds=4),
            ),
        ]

        class MockEndToEndFunction:
            def __init__(self, communicator: Communicator):
                self.communicator = communicator

            def __call__(self, *args, **kwargs):
                for m in messages:
                    with self.communicator.lock:
                        self.communicator.job.latest_status = m
                    time.sleep(0.1)

        mock_make_end_to_end_fn.side_effect = MockEndToEndFunction

        client = Client(src="gradio/calculator")
        job = client.predict(5, "add", 6)

        statuses = []
        while not job.done():
            statuses.append(job.status())
            time.sleep(0.09)

        assert all(s in messages for s in statuses)

    @patch("gradio_client.client.Endpoint.make_end_to_end_fn")
    def test_messages_correct_two_concurrent(self, mock_make_end_to_end_fn):

        now = datetime.now()

        messages_1 = [
            StatusUpdate(
                code=Status.STARTING,
                eta=None,
                rank=None,
                success=None,
                queue_size=None,
                time=now,
            ),
            StatusUpdate(
                code=Status.FINISHED,
                eta=None,
                rank=None,
                queue_size=None,
                success=True,
                time=now + timedelta(seconds=4),
            ),
        ]

        messages_2 = [
            StatusUpdate(
                code=Status.IN_QUEUE,
                eta=3,
                rank=2,
                queue_size=2,
                success=None,
                time=now + timedelta(seconds=2),
            ),
            StatusUpdate(
                code=Status.IN_QUEUE,
                eta=2,
                rank=1,
                queue_size=1,
                success=None,
                time=now + timedelta(seconds=3),
            ),
        ]

        class MockEndToEndFunction:
            n_counts = 0

            def __init__(self, communicator: Communicator):
                self.communicator = communicator
                self.messages = (
                    messages_1 if MockEndToEndFunction.n_counts == 0 else messages_2
                )
                MockEndToEndFunction.n_counts += 1

            def __call__(self, *args, **kwargs):
                for m in self.messages:
                    with self.communicator.lock:
                        print(f"here: {m}")
                        self.communicator.job.latest_status = m
                    time.sleep(0.1)

        mock_make_end_to_end_fn.side_effect = MockEndToEndFunction

        client = Client(src="gradio/calculator")
        job_1 = client.predict(5, "add", 6)
        job_2 = client.predict(11, "subtract", 1)

        statuses_1 = []
        statuses_2 = []
        while not (job_1.done() and job_2.done()):
            statuses_1.append(job_1.status())
            statuses_2.append(job_2.status())
            time.sleep(0.05)

        assert all(s in messages_1 for s in statuses_1)


class TestAPIInfo:
    @pytest.mark.parametrize("trailing_char", ["/", ""])
    def test_test_endpoint_src(self, trailing_char):
        src = "https://gradio-calculator.hf.space" + trailing_char
        client = Client(src=src)
        assert (
            client.endpoints[0].deserializers[0].root_url
            == "https://gradio-calculator.hf.space/"
        )

    @pytest.mark.flaky
    def test_numerical_to_label_space(self):
        client = Client("gradio-tests/titanic-survival")
        assert client.endpoints[0].get_info() == {
            "parameters": {
                "sex": ["Any", "", "Radio"],
                "age": ["Any", "", "Slider"],
                "fare_(british_pounds)": ["Any", "", "Slider"],
            },
            "returns": {"output": ["str", "filepath to json file", "Label"]},
        }
        assert client.view_api(return_format="dict") == {
            "named_endpoints": {
                "/predict": {
                    "parameters": {
                        "sex": ["Any", "", "Radio"],
                        "age": ["Any", "", "Slider"],
                        "fare_(british_pounds)": ["Any", "", "Slider"],
                    },
                    "returns": {"output": ["str", "filepath to json file", "Label"]},
                },
                "/predict_1": {
                    "parameters": {
                        "sex": ["Any", "", "Radio"],
                        "age": ["Any", "", "Slider"],
                        "fare_(british_pounds)": ["Any", "", "Slider"],
                    },
                    "returns": {"output": ["str", "filepath to json file", "Label"]},
                },
                "/predict_2": {
                    "parameters": {
                        "sex": ["Any", "", "Radio"],
                        "age": ["Any", "", "Slider"],
                        "fare_(british_pounds)": ["Any", "", "Slider"],
                    },
                    "returns": {"output": ["str", "filepath to json file", "Label"]},
                },
            },
            "unnamed_endpoints": {},
        }

    @pytest.mark.flaky
    def test_serializable_in_mapping(self):
        client = Client("freddyaboulton/calculator")
        assert all(
            [c.__class__ == SimpleSerializable for c in client.endpoints[0].serializers]
        )

    @pytest.mark.flaky
    def test_private_space(self):
        client = Client("gradio-tests/not-actually-private-space", hf_token=HF_TOKEN)
        assert len(client.endpoints) == 3
        assert len([e for e in client.endpoints if e.is_valid]) == 2
        assert len([e for e in client.endpoints if e.is_valid and e.api_name]) == 1
        assert client.endpoints[0].get_info() == {
            "parameters": {"x": ["Any", "", "Textbox"]},
            "returns": {"output": ["Any", "", "Textbox"]},
        }
        assert client.view_api(return_format="dict") == {
            "named_endpoints": {
                "/predict": {
                    "parameters": {"x": ["Any", "", "Textbox"]},
                    "returns": {"output": ["Any", "", "Textbox"]},
                }
            },
            "unnamed_endpoints": {
                2: {
                    "parameters": {"parameter_0": ["Any", "", "Dataset"]},
                    "returns": {
                        "x": ["Any", "", "Textbox"],
                        "output": ["Any", "", "Textbox"],
                    },
                }
            },
        }
