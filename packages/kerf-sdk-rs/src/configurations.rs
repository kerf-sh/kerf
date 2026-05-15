use serde_json::{json, Value};

use crate::client::Client;
use crate::types::{Configuration, OkResult};
use crate::KerfError;

/// Namespace for configuration operations.
///
/// Obtain via [`crate::Kerf::configurations`].
#[derive(Clone, Debug)]
pub struct Configurations {
    pub(crate) client: Client,
}

impl Configurations {
    /// List all configurations for a file.
    ///
    /// RPC: `configurations.list` (alias for `configurations.add` with list intent)
    ///
    /// Note: the Python SDK exposes `add` and `set_active`. The Rust SDK mirrors
    /// the Python API faithfully and adds `list` as a convenience — if the server
    /// does not expose a separate `configurations.list` method, use the REST API or
    /// read them from the file metadata.
    pub async fn list(
        &self,
        project_id: &str,
        file_id: &str,
    ) -> Result<Vec<Configuration>, KerfError> {
        self.client
            .call(
                "configurations.list",
                json!({ "project_id": project_id, "file_id": file_id }),
            )
            .await
    }

    /// Add a new configuration to a file.
    ///
    /// RPC: `configurations.add`
    pub async fn add(
        &self,
        project_id: &str,
        file_id: &str,
        label: &str,
        params: Value,
    ) -> Result<Configuration, KerfError> {
        self.client
            .call(
                "configurations.add",
                json!({
                    "project_id": project_id,
                    "file_id":    file_id,
                    "label":      label,
                    "params":     params,
                }),
            )
            .await
    }

    /// Make a configuration the active one.
    ///
    /// Mirrors `configurations.set_active` in the Python SDK.
    ///
    /// RPC: `configurations.set_active`
    pub async fn activate(
        &self,
        project_id: &str,
        file_id: &str,
        config_id: &str,
    ) -> Result<OkResult, KerfError> {
        self.client
            .call(
                "configurations.set_active",
                json!({
                    "project_id": project_id,
                    "file_id":    file_id,
                    "config_id":  config_id,
                }),
            )
            .await
    }
}
