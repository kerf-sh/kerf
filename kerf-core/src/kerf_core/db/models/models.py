from datetime import datetime
import uuid

from sqlalchemy import Column, String, Boolean, DateTime, Text, Index, CheckConstraint, Integer, BigInteger, Numeric, LargeBinary, PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(Text, nullable=True)
    google_id = Column(Text, unique=True, nullable=True)
    name = Column(Text, nullable=False, default="")
    avatar_url = Column(Text, nullable=False, default="")
    account_role = Column(Text, nullable=False, default="user")
    is_system = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    avatar_storage_key = Column(Text, nullable=True)
    avatar_updated_at = Column(DateTime(timezone=True), nullable=True)
    is_verified_publisher = Column(Boolean, nullable=False, default=False)
    preferences = Column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        CheckConstraint("account_role IN ('user','admin','system')", name="users_account_role_check"),
        Index("users_account_role_idx", "account_role"),
        Index("users_is_verified_publisher_idx", "is_verified_publisher", postgresql_where=(is_verified_publisher == True)),
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    token_hash = Column(Text, unique=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (Index("refresh_tokens_user_id_idx", "user_id"),)


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug = Column(Text, unique=True, nullable=False)
    name = Column(Text, nullable=False)
    avatar_storage_key = Column(Text, nullable=True)
    created_by = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (Index("workspaces_slug_idx", "slug"),)


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"

    workspace_id = Column(UUID(as_uuid=True), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    role = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        PrimaryKeyConstraint('workspace_id', 'user_id'),
        CheckConstraint("role IN ('owner','admin','member')", name="workspace_members_role_check"),
        Index("workspace_members_user_idx", "user_id"),
    )


class WorkspaceInvite(Base):
    __tablename__ = "workspace_invites"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), nullable=False)
    email = Column(String, nullable=False)
    role = Column(Text, nullable=False)
    token = Column(Text, unique=True, nullable=False)
    created_by = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("role IN ('owner','admin','member')", name="workspace_invites_role_check"),
        Index("workspace_invites_workspace_idx", "workspace_id"),
        Index("workspace_invites_email_idx", "email"),
    )


class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), nullable=False)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=False, default="")
    visibility = Column(Text, nullable=False, default="private")
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    thumbnail_storage_key = Column(Text, nullable=True)
    thumbnail_updated_at = Column(DateTime(timezone=True), nullable=True)
    tags = Column(ARRAY(Text), nullable=False, default=list)

    __table_args__ = (
        CheckConstraint("visibility IN ('private','unlisted','public')", name="projects_visibility_check"),
        Index("projects_workspace_id_idx", "workspace_id"),
        Index("projects_tags_gin_idx", "tags", postgresql_using="gin"),
    )


class File(Base):
    __tablename__ = "files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    parent_id = Column(UUID(as_uuid=True), nullable=True)
    name = Column(Text, nullable=False)
    kind = Column(Text, nullable=False, default="file")
    content = Column(Text, nullable=False, default="")
    storage_key = Column(Text, nullable=True)
    mime_type = Column(Text, nullable=True)
    size = Column(BigInteger, nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    mesh_storage_key = Column(Text, nullable=True)
    extension = Column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("kind IN ('file','folder','assembly','step','drawing','sketch','part','feature','circuit','equations','material','simulation','script','step-ref','assembly_lock','canvas','schedule','view','sheet','stair','railing','curtain_wall','graph')", name="files_kind_check"),
        Index("files_project_id_idx", "project_id"),
        Index("files_parent_id_idx", "parent_id"),
        Index("files_storage_key_idx", "storage_key"),
        Index("files_deleted_at_idx", "deleted_at"),
        Index("files_extension_idx", "extension"),
    )


class FileRevision(Base):
    __tablename__ = "file_revisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_id = Column(UUID(as_uuid=True), nullable=False)
    content = Column(Text, nullable=False)
    source = Column(Text, nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    content_sha256 = Column(LargeBinary, nullable=True)
    kind = Column(Text, nullable=False, default="base")
    content_gz = Column(LargeBinary, nullable=True)
    parent_revision_id = Column(UUID(as_uuid=True), nullable=True)
    content_preview = Column(Text, nullable=True)

    __table_args__ = (
        Index("file_revisions_file_id_created_at_idx", "file_id", "created_at"),
        Index("file_revisions_file_id_kind_idx", "file_id", "kind"),
    )


class ShareLink(Base):
    __tablename__ = "share_links"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    token = Column(Text, unique=True, nullable=False)
    role = Column(Text, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    max_uses = Column(Integer, nullable=True)
    uses = Column(Integer, nullable=False, default=0)
    created_by = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (Index("share_links_project_id_idx", "project_id"),)


class ChatThread(Base):
    __tablename__ = "chat_threads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    file_id = Column(UUID(as_uuid=True), nullable=True)
    title = Column(Text, nullable=False, default="")
    is_starred = Column(Boolean, nullable=False, default=False)
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    model = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("chat_threads_project_id_idx", "project_id"),
        Index("chat_threads_file_id_idx", "file_id"),
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id = Column(UUID(as_uuid=True), nullable=False)
    role = Column(Text, nullable=False)
    content = Column(Text, nullable=False, default="")
    part_refs = Column(JSONB, nullable=False, default=list)
    tool_calls = Column(JSONB, nullable=False, default=list)
    tool_call_id = Column(Text, nullable=True)
    model = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (Index("chat_messages_thread_id_idx", "thread_id"),)


class APIToken(Base):
    __tablename__ = "api_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    token_hash = Column(Text, unique=True, nullable=False)
    name = Column(Text, nullable=False)
    scopes = Column(JSONB, nullable=False, default=list)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("api_tokens_workspace_idx", "workspace_id"),
        Index("api_tokens_user_idx", "user_id"),
        Index("api_tokens_token_hash_idx", "token_hash"),
    )


class DerivedArtifact(Base):
    __tablename__ = "derived_artifacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_file_id = Column(UUID(as_uuid=True), nullable=False)
    content_sha256 = Column(Text, nullable=False)
    derived_kind = Column(Text, nullable=False)
    payload = Column(LargeBinary, nullable=False)
    payload_size_bytes = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    last_accessed_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("derived_artifacts_key_idx", "source_file_id", "content_sha256", "derived_kind", unique=True),
        Index("derived_artifacts_lru_idx", "last_accessed_at"),
    )


class StepTessellationJob(Base):
    __tablename__ = "step_tessellation_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_id = Column(UUID(as_uuid=True), nullable=False)
    status = Column(Text, nullable=False, default="queued")
    error = Column(Text, nullable=True)
    mesh_storage_key = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("status IN ('queued','running','done','error')", name="step_tessellation_jobs_status_check"),
        Index("step_tessellation_jobs_status_idx", "status", "created_at", postgresql_where=(status.in_(["queued", "running"]))),
        Index("step_tessellation_jobs_file_id_unique", "file_id", unique=True),
    )


class SimJob(Base):
    __tablename__ = "sim_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_id = Column(UUID(as_uuid=True), nullable=False)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    status = Column(Text, nullable=False, default="queued")
    input_spec = Column(JSONB, nullable=False, default=dict)
    result_json = Column(JSONB, nullable=True)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("status IN ('queued','running','done','error')", name="sim_jobs_status_check"),
        Index("sim_jobs_status_idx", "status", "created_at", postgresql_where=(status.in_(["queued", "running"]))),
        Index("sim_jobs_file_id_unique", "file_id", unique=True),
    )


class FemJob(Base):
    __tablename__ = "fem_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_id = Column(UUID(as_uuid=True), nullable=False)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    status = Column(Text, nullable=False, default="queued")
    input_spec = Column(JSONB, nullable=False, default=dict)
    result_json = Column(JSONB, nullable=True)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("status IN ('queued','running','done','error')", name="fem_jobs_status_check"),
        Index("fem_jobs_status_idx", "status", "created_at", postgresql_where=(status.in_(["queued", "running"]))),
        Index("fem_jobs_file_id_unique", "file_id", unique=True),
    )


class CamJob(Base):
    __tablename__ = "cam_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_id = Column(UUID(as_uuid=True), nullable=False)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    status = Column(Text, nullable=False, default="queued")
    input_spec = Column(JSONB, nullable=False, default=dict)
    result_json = Column(JSONB, nullable=True)
    output_key = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("status IN ('queued','running','done','error')", name="cam_jobs_status_check"),
        Index("cam_jobs_status_idx", "status", "created_at", postgresql_where=(status.in_(["queued", "running"]))),
        Index("cam_jobs_file_id_unique", "file_id", unique=True, postgresql_where=(status.in_(["queued", "running"]))),
    )


class UsageEvent(Base):
    __tablename__ = "usage_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    project_id = Column(UUID(as_uuid=True), nullable=True)
    kind = Column(Text, nullable=False)
    model = Column(Text, nullable=True)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    bytes_delta = Column(BigInteger, nullable=False, default=0)
    usd_cost = Column(Numeric(12, 6), nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("usage_events_user_id_idx", "user_id", "created_at"),
        Index("usage_events_project_id_idx", "project_id", "created_at"),
        Index("usage_events_kind_idx", "kind", "created_at"),
    )


class UploadSession(Base):
    __tablename__ = "upload_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    filename = Column(Text, nullable=False)
    size = Column(BigInteger, nullable=False)
    mime = Column(Text, nullable=True)
    sha256 = Column(Text, nullable=False)
    storage_key = Column(Text, nullable=False)
    chunk_size = Column(Integer, nullable=False, default=5242880)
    total_chunks = Column(Integer, nullable=False)
    received_chunks = Column(ARRAY(Integer), nullable=False, default=list)
    bytes_received = Column(BigInteger, nullable=False, default=0)
    complete = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("upload_sessions_project_id_expires_idx", "project_id", "expires_at"),
        Index("upload_sessions_sha256_idx", "project_id", "sha256"),
    )


class LibraryPartSubmission(Base):
    __tablename__ = "library_part_submissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submitter_user_id = Column(UUID(as_uuid=True), nullable=False)
    target_workspace_id = Column(UUID(as_uuid=True), nullable=False)
    payload = Column(JSONB, nullable=False)
    status = Column(Text, nullable=False, default="pending")
    review_note = Column(Text, nullable=False, default="")
    reviewer_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("library_part_submissions_status_idx", "status"),
        Index("library_part_submissions_submitter_idx", "submitter_user_id"),
        Index("library_part_submissions_target_idx", "target_workspace_id"),
    )


class DistributorCredential(Base):
    __tablename__ = "distributor_credentials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, unique=True, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    secret_encrypted = Column(LargeBinary, nullable=False)
    rate_limit_per_minute = Column(Integer, nullable=False, default=60)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (Index("distributor_credentials_enabled_idx", "enabled", postgresql_where=(enabled == True)),)
