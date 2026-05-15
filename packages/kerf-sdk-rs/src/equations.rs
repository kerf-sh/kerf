use serde_json::json;

use crate::client::Client;
use crate::types::{EquationsMap, OkResult};
use crate::KerfError;

/// Namespace for equation operations.
///
/// Obtain via [`crate::Kerf::equations`].
#[derive(Clone, Debug)]
pub struct Equations {
    pub(crate) client: Client,
}

impl Equations {
    /// Read all equations for a file.
    ///
    /// RPC: `equations.read`
    pub async fn read(&self, project_id: &str, file_id: &str) -> Result<EquationsMap, KerfError> {
        self.client
            .call(
                "equations.read",
                json!({ "project_id": project_id, "file_id": file_id }),
            )
            .await
    }

    /// Set (create or update) a named equation.
    ///
    /// RPC: `equations.set`
    pub async fn set(
        &self,
        project_id: &str,
        file_id: &str,
        name: &str,
        expression: &str,
    ) -> Result<OkResult, KerfError> {
        self.client
            .call(
                "equations.set",
                json!({
                    "project_id": project_id,
                    "file_id":    file_id,
                    "name":       name,
                    "expression": expression,
                }),
            )
            .await
    }
}
