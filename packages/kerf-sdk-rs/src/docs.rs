use serde_json::json;

use crate::client::Client;
use crate::types::DocHit;
use crate::KerfError;

/// Namespace for documentation search.
///
/// Obtain via [`crate::Kerf::docs`].
#[derive(Clone, Debug)]
pub struct Docs {
    pub(crate) client: Client,
}

impl Docs {
    /// Search the Kerf documentation.
    ///
    /// `k` optionally limits the number of results returned (server default if `None`).
    ///
    /// RPC: `docs.search`
    pub async fn search(&self, query: &str, k: Option<u32>) -> Result<Vec<DocHit>, KerfError> {
        let mut params = json!({ "query": query });
        if let Some(n) = k {
            params["k"] = serde_json::Value::Number(n.into());
        }
        self.client.call("docs.search", params).await
    }
}
