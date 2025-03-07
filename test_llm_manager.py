import pytest
from unittest.mock import patch, MagicMock
from llm_manager import LLMManager

@pytest.fixture
def llm_manager():
    with patch.dict('os.environ', {
        'LLM_PROVIDER': 'openai',
        'OPENAI_MODEL': 'o3-mini',
        'OPENAI_API_KEY': 'test-key',
        'STORY_POINTS_FIELD': 'customfield_10025',
        'JIRA_BASE_URL': 'https://test.atlassian.net'
    }):
        return LLMManager()

def test_get_model_string(llm_manager):
    assert llm_manager.get_model_string() == 'o3-mini'  # OpenAI model doesn't need provider prefix
    
    # Test switching provider
    llm_manager.switch_provider('anthropic')
    assert llm_manager.get_model_string().startswith('anthropic/')

@patch('llm_manager.completion')
def test_process_message_no_function_call(mock_completion, llm_manager):
    # Mock a simple response with no function calls
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message = MagicMock()
    mock_response.choices[0].message.tool_calls = None
    mock_response.choices[0].message.content = "Test response"
    
    mock_completion.return_value = mock_response
    
    result = llm_manager.process_message("Test message")
    assert result == "Test response"
    
    # Verify completion was called with correct parameters
    mock_completion.assert_called_once()
    call_args = mock_completion.call_args[1]
    assert call_args['model'] == 'o3-mini'  # OpenAI model doesn't need provider prefix
    assert call_args['messages'][-1]['content'] == "Test message"
    assert 'tools' in call_args

@patch('llm_manager.completion')
def test_process_message_with_function_call(mock_completion, llm_manager):
    # Mock a response with function calls
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message = MagicMock()
    
    # Create a tool call
    tool_call = MagicMock()
    tool_call.id = "call_123"
    tool_call.function = MagicMock()
    tool_call.function.name = "get_project_metrics"
    tool_call.function.arguments = '{"project_keys": ["XYZ"], "num_sprints": 3}'
    
    mock_response.choices[0].message.tool_calls = [tool_call]
    
    # Mock the followup response
    mock_followup = MagicMock()
    mock_followup.choices = [MagicMock()]
    mock_followup.choices[0].message = MagicMock()
    mock_followup.choices[0].message.content = "Function result"
    
    # Set up the mock to return different values on consecutive calls
    mock_completion.side_effect = [mock_response, mock_followup]
    
    # Mock the get_metrics function
    with patch('metrics_manager.get_metrics', return_value={"test": "data"}):
        result = llm_manager.process_message("Get metrics for XYZ")
    
    assert result == "Function result"
    assert mock_completion.call_count == 2

@patch('llm_manager.completion')
def test_fallback_mechanism(mock_completion, llm_manager):
    # Set up the manager to use anthropic with fallback to openai
    llm_manager.provider = "anthropic"
    llm_manager.model = "anthropic/claude-3-opus-20240229"
    llm_manager.fallbacks = ["o3-mini"]  # OpenAI model doesn't need provider prefix
    
    # Mock a simple response
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message = MagicMock()
    mock_response.choices[0].message.tool_calls = None
    mock_response.choices[0].message.content = "Fallback response"
    
    mock_completion.return_value = mock_response
    
    result = llm_manager.process_message("Test message")
    assert result == "Fallback response"
    
    # Verify completion was called with fallbacks
    mock_completion.assert_called_once()
    call_args = mock_completion.call_args[1]
    assert call_args['model'] == 'anthropic/claude-3-opus-20240229'
    assert call_args['fallbacks'] == ["o3-mini"]  # OpenAI model doesn't need provider prefix

@patch('llm_manager.completion')
def test_error_handling(mock_completion, llm_manager):
    # Make the completion function raise an exception
    mock_completion.side_effect = Exception("Test error")
    
    # Test that the error is handled gracefully
    result = llm_manager.process_message("Test message")
    assert "I encountered an error: Test error" in result
