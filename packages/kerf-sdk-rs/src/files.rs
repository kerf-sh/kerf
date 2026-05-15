use serde_json::json;

use crate::client::Client;
use crate::types::{FileContent, FileInfo, OkResult};
use crate::KerfError;

/// Namespace for file operations.
///
/// Obtain via [`crate::Kerf::files`].
#[derive(Clone, Debug)]
pub struct Files {
    pub(crate) client: Client,
}

impl Files {
    /// List all files in a project.
    ///
    /// RPC: `files.list`
    pub async fn list(&self, project_id: &str) -> Result<Vec<FileInfo>, KerfError> {
        self.client
            .call("files.list", json!({ "project_id": project_id }))
            .await
    }

    /// Read a single file's content and metadata.
    ///
    /// RPC: `files.read`
    pub async fn read(&self, project_id: &str, file_id: &str) -> Result<FileContent, KerfError> {
        self.client
            .call(
                "files.read",
                json!({ "project_id": project_id, "file_id": file_id }),
            )
            .await
    }

    /// Overwrite a file's content.
    ///
    /// RPC: `files.write`
    pub async fn write(
        &self,
        project_id: &str,
        file_id: &str,
        content: &str,
    ) -> Result<OkResult, KerfError> {
        self.client
            .call(
                "files.write",
                json!({
                    "project_id": project_id,
                    "file_id":   file_id,
                    "content":   content,
                }),
            )
            .await
    }

    /// Apply a string edit to a file (old_string → new_string).
    ///
    /// RPC: `files.edit`
    pub async fn edit(
        &self,
        project_id: &str,
        file_id: &str,
        old_string: &str,
        new_string: &str,
    ) -> Result<OkResult, KerfError> {
        self.client
            .call(
                "files.edit",
                json!({
                    "project_id": project_id,
                    "file_id":    file_id,
                    "old_string": old_string,
                    "new_string": new_string,
                }),
            )
            .await
    }

    /// Create a new file.
    ///
    /// `kind` defaults to `"file"`. `parent_id` is optional.
    ///
    /// RPC: `files.create`
    pub async fn create(
        &self,
        project_id: &str,
        name: &str,
        kind: &str,
        content: &str,
        parent_id: Option<&str>,
    ) -> Result<FileInfo, KerfError> {
        let mut params = json!({
            "project_id": project_id,
            "name":       name,
            "kind":       kind,
            "content":    content,
        });
        if let Some(pid) = parent_id {
            params["parent_id"] = serde_json::Value::String(pid.to_owned());
        }
        self.client.call("files.create", params).await
    }

    /// Delete a file.
    ///
    /// RPC: `files.delete`
    pub async fn delete(&self, project_id: &str, file_id: &str) -> Result<OkResult, KerfError> {
        self.client
            .call(
                "files.delete",
                json!({ "project_id": project_id, "file_id": file_id }),
            )
            .await
    }

    /// Full-text search across file contents in a project.
    ///
    /// RPC: `files.search`
    pub async fn search(
        &self,
        project_id: &str,
        query: &str,
    ) -> Result<Vec<serde_json::Value>, KerfError> {
        self.client
            .call(
                "files.search",
                json!({ "project_id": project_id, "query": query }),
            )
            .await
    }
}
