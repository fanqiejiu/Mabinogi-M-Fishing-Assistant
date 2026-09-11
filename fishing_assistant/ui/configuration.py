"""主窗口配置 Mixin 聚合入口。"""

from .config.binding import ConfigurationBindingMixin
from .config.fishing import FishingConfigurationMixin
from .config.profile import ProfileConfigurationMixin
from .config.settings import SettingsConfigurationMixin
from .config.threshold import ThresholdConfigurationMixin


class ConfigurationMixin(ProfileConfigurationMixin, SettingsConfigurationMixin, ConfigurationBindingMixin, FishingConfigurationMixin, ThresholdConfigurationMixin):
    """组合各页面配置能力，保持 MainWindow 的原有接口。"""
