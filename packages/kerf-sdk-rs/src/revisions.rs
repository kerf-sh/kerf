use serde_json::json;

use crate::client::Client;
use crate::types::{OkResult, RevisionContent, RevisionInfo};
use crate::KerfError;

/// Namespace for revision / history operations.
///
/// Obtain via [`crate::Kerf::revisions`].
#[derive(Clone, Debug)]
pub struct Revisions {
    pub(crate) client: Client,
}

impl Revisions {
    /// List revisions for a file.
    ///
    /// `limit` caps the number of entries returned (omit for server default).
    ///
    /// RPC: `revisions.list`
    pub async fn list(
        &self,
        project_id: &str,
        file_id: &str,
        limit: Option<u32>,
    ) -> Result<Vec<RevisionInfo>, KerfError> {
        let mut params = json!({ "project_id": project_id, "file_id": file_id });
        if let Some(n) = limit {
            params["limit"] = serde_json::Value::Number(n.into());
        }
        self.client.call("revisions.list", params).await
    }

    /// Read the content of a file at a specific revision.
    ///
    /// RPC: `revisions.read`
    pub async fn read(
        &self,
        project_id: &str,
        file_id: &str,
        revision_id: &str,
    ) -> Result<RevisionContent, KerfError> {
        self.client
            .call(
                "revisions.read",
                json!({
                    "project_id":   project_id,
                    "file_id":      file_id,
                    "revision_id":  revision_id,
                }),
            )
            .await
    }

    /// Restore a file to a previous revision.
    ///
    /// RPC: `revisions.restore`
    pub async fn restore(
        &self,
        project_id: &str,
        file_id: &str,
        revision_id: &str,
    ) -> Result<OkResult, KerfError> {
        self.client
            .call(
                "revisions.restore",
                json!({
                    "project_id":  project_id,
                    "file_id":     file_id,
                    "revision_id": revision_id,
                }),
            )
            .await
    }
}
