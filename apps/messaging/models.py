"""Unified inbox: user-to-user threads + system notifications.

`Thread` groups related `Message`s. A thread has 1..N `Participant`s
(tenant users) plus an optional `kind` flag indicating whether this is
a user thread or a system-generated notification thread (used by the
automation engine).

Read state lives on `Participant.last_read_at`; the unread count for a
user is the number of messages in their threads with
`created_at > Participant.last_read_at`.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TenantOwnedModel


class MessagingArea(models.Model):
    class Meta:
        managed = False
        default_permissions = ()
        permissions = (
            ("view_messaging", "Can view messages"),
            ("manage_messaging", "Can manage messages"),
        )


class Thread(TenantOwnedModel):
    class Kind(models.TextChoices):
        DIRECT = "DIRECT", "Direct message"
        GROUP = "GROUP", "Group conversation"
        NOTIFICATION = "NOTIFICATION", "System notification"

    subject = models.CharField(max_length=200, blank=True)
    kind = models.CharField(max_length=15, choices=Kind.choices, default=Kind.DIRECT)
    last_message_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("-last_message_at",)
        indexes = [models.Index(fields=["tenant", "-last_message_at"])]

    def __str__(self) -> str:
        return self.subject or f"thread#{self.pk}"


class Participant(TenantOwnedModel):
    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name="participants")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="thread_memberships"
    )
    joined_at = models.DateTimeField(default=timezone.now)
    last_read_at = models.DateTimeField(null=True, blank=True)
    is_muted = models.BooleanField(default=False)

    class Meta:
        unique_together = (("tenant", "thread", "user"),)
        indexes = [models.Index(fields=["tenant", "user"])]

    def __str__(self) -> str:
        return f"{self.user} in {self.thread}"


class Message(TenantOwnedModel):
    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_messages",
        help_text="NULL for system-generated notifications.",
    )
    body = models.TextField()
    is_system = models.BooleanField(
        default=False,
        help_text="True for messages emitted by the automation engine.",
    )

    class Meta:
        ordering = ("pk",)
        indexes = [models.Index(fields=["tenant", "thread", "id"])]

    def __str__(self) -> str:
        return f"msg#{self.pk} in {self.thread}"

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        # Only bump the thread's last_message_at on insert, and push the
        # comparison into SQL so the UPDATE is a no-op when not needed —
        # this also avoids fetching `self.thread` (an extra SELECT) when the
        # caller didn't pre-populate it.
        if is_new and self.thread_id:
            Thread.unscoped.filter(
                pk=self.thread_id, last_message_at__lt=self.created_at
            ).update(last_message_at=self.created_at)


def send_direct_message(*, tenant, sender, recipient, body: str, subject: str = "") -> Message:
    """Convenience helper used by trigger actions and DMs alike.

    Finds or creates a DIRECT thread between `sender` and `recipient`
    (within the tenant), appends the message.
    """
    # Look for an existing 1:1 DIRECT thread with exactly these two participants.
    candidate_threads = Thread.unscoped.filter(
        tenant=tenant, kind=Thread.Kind.DIRECT, participants__user=sender
    ).filter(participants__user=recipient).distinct()
    thread = candidate_threads.first()
    if thread is None:
        thread = Thread.unscoped.create(tenant=tenant, kind=Thread.Kind.DIRECT, subject=subject)
        Participant.unscoped.create(tenant=tenant, thread=thread, user=sender)
        Participant.unscoped.create(tenant=tenant, thread=thread, user=recipient)
    msg = Message.unscoped.create(tenant=tenant, thread=thread, sender=sender, body=body)
    return msg


def send_notification(*, tenant, recipient, body: str, subject: str = "Notification") -> Message:
    """Create or reuse the user's NOTIFICATION inbox thread and post a message."""
    thread = Thread.unscoped.filter(
        tenant=tenant, kind=Thread.Kind.NOTIFICATION, participants__user=recipient
    ).first()
    if thread is None:
        thread = Thread.unscoped.create(tenant=tenant, kind=Thread.Kind.NOTIFICATION, subject=subject)
        Participant.unscoped.create(tenant=tenant, thread=thread, user=recipient)
    msg = Message.unscoped.create(
        tenant=tenant, thread=thread, sender=None, body=body, is_system=True
    )
    return msg
