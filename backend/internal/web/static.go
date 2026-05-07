// Package web hosts the embedded frontend bundle.
//
// The Vite build outputs to ./dist (set via build.outDir in vite.config.js).
// The placeholder .gitkeep keeps the directory present in git so this
// package compiles even on a fresh clone where `npm run build` hasn't run
// yet — at runtime, HasContent() reports whether the bundle is populated
// and main.go skips the SPA handler when it isn't (dev mode).
package web

import (
	"embed"
	"io/fs"
)

//go:embed all:dist
var distFS embed.FS

// Sub returns the embedded dist/ directory rooted (so paths inside callers
// look like "index.html", not "dist/index.html"). Returns an empty FS if
// the bundle hasn't been built yet.
func Sub() (fs.FS, bool) {
	sub, err := fs.Sub(distFS, "dist")
	if err != nil {
		return nil, false
	}
	if !HasContent() {
		return sub, false
	}
	return sub, true
}

// HasContent reports whether the dist bundle has been populated with a real
// Vite build. Cheap check: looks for index.html.
func HasContent() bool {
	f, err := distFS.Open("dist/index.html")
	if err != nil {
		return false
	}
	_ = f.Close()
	return true
}
