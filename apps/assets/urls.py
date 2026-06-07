from apps.core.crud import ModuleCRUDConfig, build_module_urls

from .models import Asset, AssetCategory


class AssetCategoryConfig(ModuleCRUDConfig):
    model = AssetCategory
    fields = ["code", "name", "depreciation_method", "useful_life_months"]
    list_display = ["code", "name", "depreciation_method", "useful_life_months"]
    url_namespace = "assets"
    module_code = "assets"


class AssetConfig(ModuleCRUDConfig):
    model = Asset
    fields = ["asset_no", "name", "category", "acquisition_date", "cost", "location", "status"]
    list_display = ["asset_no", "name", "category", "status", "cost"]
    list_select_related = ["category"]
    url_namespace = "assets"
    module_code = "assets"


urlpatterns = build_module_urls(AssetCategoryConfig) + build_module_urls(AssetConfig)
