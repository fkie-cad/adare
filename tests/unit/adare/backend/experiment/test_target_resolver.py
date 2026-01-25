
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path
from adare.backend.experiment.target_resolver import MCPTargetResolver, TargetMatch, MCPConditionChecker
from adare.types.playbook import Target, BestConfidenceStrategy, TopLeftStrategy, ExistsCondition, NotExistsCondition

@pytest.fixture
def experiment_dir(tmp_path):
    return tmp_path / "experiment"

@pytest.fixture
def resolver(experiment_dir):
    return MCPTargetResolver(experiment_dir=experiment_dir)

class TestMCPTargetResolver:

    @pytest.mark.asyncio
    async def test_test_mcp_connection_success(self, resolver):
        with patch('adare.backend.experiment.target_resolver.Client') as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            
            result = await resolver.test_mcp_connection()
            
            assert result is True
            assert resolver._connection_available is True

    @pytest.mark.asyncio
    async def test_test_mcp_connection_failure(self, resolver):
        with patch('adare.backend.experiment.target_resolver.Client') as mock_client_cls:
            mock_client_cls.return_value.__aenter__.side_effect = Exception("Connection refused")
            
            result = await resolver.test_mcp_connection()
            
            assert result is False
            assert resolver._connection_available is False

    @pytest.mark.asyncio
    async def test_resolve_target_position(self, resolver):
        target = Target(position=[100, 200])
        match = await resolver.resolve_target(target)
        
        assert match.coordinates == (100, 200)
        assert match.method == 'position'

    @pytest.mark.asyncio
    async def test_resolve_target_image_success(self, resolver):
        target = Target(image="icon.png", strategy=BestConfidenceStrategy())
        screenshot = "base64screenshot"
        
        # Mock file reading
        with patch("builtins.open", new_callable=MagicMock) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = b"iconbytes"
            
            with patch('adare.backend.experiment.target_resolver.Client') as mock_client_cls:
                mock_client = AsyncMock()
                mock_client_cls.return_value.__aenter__.return_value = mock_client
                
                # Mock find_icon result
                mock_result = MagicMock()
                mock_result.data = {
                    "locations": [[10, 10], [20, 20]],
                    "similarities": [0.95, 0.85]
                }
                mock_client.call_tool.return_value = mock_result
                
                match = await resolver.resolve_target(target, screenshot_base64=screenshot)
                
                assert match is not None
                assert match.coordinates == (10, 10)
                assert match.confidence == 0.95

    @pytest.mark.asyncio
    async def test_resolve_target_text_success(self, resolver):
        target = Target(text="Login", strategy=TopLeftStrategy())
        screenshot = "base64screenshot"
        
        with patch('adare.backend.experiment.target_resolver.Client') as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            
            # Mock find_text result
            mock_result = MagicMock()
            mock_result.data = {
                "locations": [
                    {"location": {"x": 100, "y": 100}, "text": "Login"},
                    {"location": {"x": 50, "y": 200}, "text": "Login"} # Lower down
                ],
                "confidences": [0.9, 0.8]
            }
            mock_client.call_tool.return_value = mock_result
            
            match = await resolver.resolve_target(target, screenshot_base64=screenshot)
            
            assert match is not None
            # TopLefftStrategy should pick y=100 over y=200
            assert match.coordinates == (100, 100)

    def test_select_match_by_strategy_best_confidence(self, resolver):
        matches = [
            TargetMatch(coordinates=(10, 10), confidence=0.8, method='image'),
            TargetMatch(coordinates=(20, 20), confidence=0.9, method='image')
        ]
        
        selected = resolver._select_match_by_strategy(matches, BestConfidenceStrategy())
        assert selected.coordinates == (20, 20)

    def test_select_match_by_strategy_top_left(self, resolver):
        matches = [
            TargetMatch(coordinates=(100, 100), confidence=0.9, method='image'), # Bottom Right
            TargetMatch(coordinates=(10, 10), confidence=0.9, method='image')    # Top Left
        ]
        
        selected = resolver._select_match_by_strategy(matches, TopLeftStrategy())
        assert selected.coordinates == (10, 10)


class TestMCPConditionChecker:
    @pytest.mark.asyncio
    async def test_check_conditions_exists_met(self):
        resolver = AsyncMock(spec=MCPTargetResolver)
        resolver.resolve_target.return_value = TargetMatch((0,0), 1.0, 'mock')
        
        checker = MCPConditionChecker(resolver)
        condition = ExistsCondition(text="Submit")
        
        result = await checker.check_conditions([condition], "scr")
        assert result is True

    @pytest.mark.asyncio
    async def test_check_conditions_exists_failed(self):
        resolver = AsyncMock(spec=MCPTargetResolver)
        resolver.resolve_target.return_value = None
        
        checker = MCPConditionChecker(resolver)
        condition = ExistsCondition(text="Submit")
        
        result = await checker.check_conditions([condition], "scr")
        assert result is False

    @pytest.mark.asyncio
    async def test_check_conditions_not_exists_met(self):
        resolver = AsyncMock(spec=MCPTargetResolver)
        resolver.resolve_target.return_value = None
        
        checker = MCPConditionChecker(resolver)
        condition = NotExistsCondition(text="Error")
        
        result = await checker.check_conditions([condition], "scr")
        assert result is True
