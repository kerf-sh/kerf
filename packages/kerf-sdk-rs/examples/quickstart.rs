//! Quickstart for kerf-sdk-rs.
//!
//! Run with:
//!   KERF_API_URL=https://kerf.sh KERF_API_TOKEN=ktok_... cargo run --example quickstart \
//!     --manifest-path packages/kerf-sdk-rs/Cargo.toml
//!
//! The example mirrors `examples/kerf_sdk_example.py` from the Python SDK.

use kerf_sdk::Kerf;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // -----------------------------------------------------------------------
    // 1. Build a client from environment variables
    // -----------------------------------------------------------------------
    let k = Kerf::from_env()?;

    // -----------------------------------------------------------------------
    // 2. List files in a project
    // -----------------------------------------------------------------------
    let project_id = std::env::var("KERF_PROJECT_ID")
        .unwrap_or_else(|_| "proj_your_project_id_here".into());

    println!("Listing files in project {project_id}...");
    let files = k.files.list(&project_id).await?;
    println!("Found {} file(s):", files.len());
    for f in &files {
        println!("  - {} ({}) [{}]", f.name, f.kind, f.id);
    }

    // -----------------------------------------------------------------------
    // 3. Read the first file if one exists
    // -----------------------------------------------------------------------
    if let Some(first) = files.first() {
        println!("\nReading file \"{}\"...", first.name);
        let content = k.files.read(&project_id, &first.id).await?;
        let preview = content.content.chars().take(120).collect::<String>();
        println!("Content preview: {preview:?}");
    }

    // -----------------------------------------------------------------------
    // 4. Set an equation
    // -----------------------------------------------------------------------
    if let Some(first) = files.first() {
        println!("\nSetting equation width=25mm on file {}...", first.id);
        let result = k
            .equations
            .set(&project_id, &first.id, "width", "25 mm")
            .await?;
        println!("Set result: ok={}", result.ok);
    }

    // -----------------------------------------------------------------------
    // 5. Search docs
    // -----------------------------------------------------------------------
    println!("\nSearching documentation for \"assemblies\"...");
    let hits = k.docs.search("assemblies", Some(3)).await?;
    println!("Doc hits:");
    for hit in &hits {
        println!("  - {}: {}", hit.title, hit.url);
    }

    // -----------------------------------------------------------------------
    // 6. List revisions of the first file
    // -----------------------------------------------------------------------
    if let Some(first) = files.first() {
        println!("\nListing revisions for file {}...", first.id);
        let revs = k.revisions.list(&project_id, &first.id, Some(5)).await?;
        println!("Revisions (last {}):", revs.len());
        for rev in &revs {
            println!(
                "  - {} at {}",
                rev.id,
                rev.created_at.as_deref().unwrap_or("unknown")
            );
        }
    }

    println!("\nDone.");
    Ok(())
}
