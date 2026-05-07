import os
import pytest
from unittest.mock import patch
from schedule_agent.agent_runner import run_agent, create_schedule_agent


class TestAgentRunner:
    def test_run_agent_no_api_key(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            result = run_agent("帮我排期")
            assert "没有配置 OPENAI_API_KEY" in result

    def test_create_agent_no_api_key(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            agent = create_schedule_agent()
            assert agent is None
