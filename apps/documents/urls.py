from apps.core.crud import ModuleCRUDConfig, build_module_urls

from .models import Document, Folder, Tag


class FolderConfig(ModuleCRUDConfig):
    model = Folder
    fields = ["name", "parent"]
    list_display = ["name", "parent"]
    list_select_related = ["parent"]
    url_namespace = "documents"
    module_code = "documents"


class DocumentConfig(ModuleCRUDConfig):
    model = Document
    fields = ["folder", "title", "file", "tags"]
    list_display = ["title", "folder", "mime_type", "size"]
    list_select_related = ["folder", "uploaded_by"]
    url_namespace = "documents"
    module_code = "documents"


class TagConfig(ModuleCRUDConfig):
    model = Tag
    fields = ["name"]
    list_display = ["name"]
    url_namespace = "documents"
    module_code = "documents"


urlpatterns = (
    build_module_urls(FolderConfig)
    + build_module_urls(DocumentConfig)
    + build_module_urls(TagConfig)
)
