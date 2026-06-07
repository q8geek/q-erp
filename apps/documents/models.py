from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TenantOwnedModel


class DocumentsArea(models.Model):
    class Meta:
        managed = False
        default_permissions = ()
        permissions = (
            ("view_documents", "Can view documents"),
            ("manage_documents", "Can manage documents"),
        )


class Tag(TenantOwnedModel):
    name = models.CharField(max_length=64)

    class Meta:
        unique_together = (("tenant", "name"),)
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class Folder(TenantOwnedModel):
    name = models.CharField(max_length=200)
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="children")

    class Meta:
        unique_together = (("tenant", "parent", "name"),)
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


def document_upload_to(instance, filename: str) -> str:
    today = timezone.now()
    return f"tenants/{instance.tenant_id}/documents/{today:%Y}/{today:%m}/{filename}"


class Document(TenantOwnedModel):
    folder = models.ForeignKey(Folder, on_delete=models.SET_NULL, null=True, blank=True, related_name="documents")
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to=document_upload_to)
    mime_type = models.CharField(max_length=120, blank=True)
    size = models.PositiveBigIntegerField(default=0)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name="documents")

    class Meta:
        ordering = ("-pk",)
        indexes = [
            models.Index(fields=["tenant", "-id"]),
        ]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        # Recompute size/mime_type on INSERT and on file replacement.
        # Metadata-only updates (e.g. retitling, retagging) must not re-read
        # self.file.size, which can hit storage on every save.
        recompute = self._state.adding
        if not recompute and self.pk and self.file:
            prev_name = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list("file", flat=True)
                .first()
            )
            recompute = bool(
                self.file.name and self.file.name != (prev_name or "")
            )
        if recompute and self.file and getattr(self.file, "name", ""):
            try:
                self.size = self.file.size
            except Exception:
                pass
            try:
                self.mime_type = (
                    getattr(self.file.file, "content_type", "") or self.mime_type
                )
            except Exception:
                pass
        super().save(*args, **kwargs)
