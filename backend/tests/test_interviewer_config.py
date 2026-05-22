"""TDD Cycle 1: InterviewerConfig 模型测试"""
import pytest
from pydantic import ValidationError


class TestInterviewerConfig:
    """InterviewerConfig 模型还未实现，这些测试应该全部失败"""

    def test_create_interviewer(self):
        """可以创建完整配置的面试官"""
        from backend.mock_interview.interviewer_config import InterviewerConfig
        config = InterviewerConfig(
            name="张工",
            role="资深工程师",
            style="严谨深入",
            focus_area="编码能力",
            prompt_template="你是一位资深工程师...",
        )
        assert config.name == "张工"
        assert config.role == "资深工程师"
        assert config.style == "严谨深入"
        assert config.focus_area == "编码能力"
        assert config.prompt_template is not None

    def test_interviewer_default_prompt(self):
        """不提供 prompt_template 时使用默认模板"""
        from backend.mock_interview.interviewer_config import InterviewerConfig
        config = InterviewerConfig(
            name="李总",
            role="技术总监",
            style="宏观开放",
            focus_area="架构设计",
        )
        assert config.prompt_template is not None
        assert "{role}" in config.prompt_template
        assert "{focus_area}" in config.prompt_template
        assert "{style}" in config.prompt_template

    def test_interviewer_name_required(self):
        """名称为空时应该校验失败"""
        from backend.mock_interview.interviewer_config import InterviewerConfig
        with pytest.raises(ValidationError):
            InterviewerConfig(name="", role="HR", style="温和", focus_area="软技能")

    def test_interviewer_multiple_focus_areas(self):
        """支持多个考察重点"""
        from backend.mock_interview.interviewer_config import InterviewerConfig
        config = InterviewerConfig(
            name="张工",
            role="资深工程师",
            style="严谨深入",
            focus_area=["编码能力", "项目深挖", "代码质量"],
        )
        assert len(config.focus_area) == 3
        assert "编码能力" in config.focus_area

    def test_interviewer_voice_style(self):
        """面试官有独立的语音风格设定"""
        from backend.mock_interview.interviewer_config import InterviewerConfig
        config = InterviewerConfig(
            name="王姐",
            role="HR负责人",
            style="温和引导",
            focus_area="软技能",
            voice_style="gentle",
        )
        assert config.voice_style == "gentle"

    def test_interviewer_to_dict(self):
        """能够序列化为字典"""
        from backend.mock_interview.interviewer_config import InterviewerConfig
        config = InterviewerConfig(
            name="张工",
            role="资深工程师",
            style="严谨深入",
            focus_area="编码能力",
        )
        d = config.to_dict()
        assert d["name"] == "张工"
        assert d["role"] == "资深工程师"
        assert d["style"] == "严谨深入"

    def test_interviewer_list_management(self):
        """面试官列表管理——添加和删除"""
        from backend.mock_interview.interviewer_config import InterviewerManager
        manager = InterviewerManager()
        gong = manager.add_interviewer(
            name="张工", role="资深工程师",
            style="严谨深入", focus_area="编码能力",
        )
        li = manager.add_interviewer(
            name="李总", role="技术总监",
            style="宏观开放", focus_area="架构设计",
        )
        assert len(manager.list_interviewers()) == 2

        manager.remove_interviewer(gong.id)
        assert len(manager.list_interviewers()) == 1
        assert manager.list_interviewers()[0].name == "李总"

    def test_interviewer_list_empty_validation(self):
        """空面试官列表不允许启动面试"""
        from backend.mock_interview.interviewer_config import InterviewerManager
        manager = InterviewerManager()
        assert not manager.has_interviewers()

    def test_interviewer_update(self):
        """可以更新面试官配置"""
        from backend.mock_interview.interviewer_config import InterviewerManager
        manager = InterviewerManager()
        gong = manager.add_interviewer(
            name="张工", role="资深工程师",
            style="严谨深入", focus_area="编码能力",
        )
        updated = manager.update_interviewer(gong.id, focus_area="系统设计")
        assert updated.focus_area == "系统设计"

    def test_render_prompt(self):
        """render_prompt 正确填充模板"""
        from backend.mock_interview.interviewer_config import InterviewerConfig
        config = InterviewerConfig(
            name="张工",
            role="资深工程师",
            style="严谨深入",
            focus_area="编码能力",
        )
        rendered = config.render_prompt()
        assert "资深工程师" in rendered
        assert "严谨深入" in rendered
        assert "编码能力" in rendered
