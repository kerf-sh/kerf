# Homebrew formula for Kerf — chat-driven CAD tool.
#
# Install via a personal tap:
#
#   brew tap imranp/kerf https://github.com/imranp/homebrew-kerf
#   brew install kerf
#
# Or directly from this repo once tagged:
#
#   brew install imranp/kerf/kerf
#
# This builds from source. Once we ship pre-built release binaries, swap
# the `url` + `sha256` to a release tarball and remove the `:build` deps.

class Kerf < Formula
  desc "Chat-driven CAD tool. JSCAD code on one side, 3D rendering on the other"
  homepage "https://github.com/imranp/kerf"
  url "https://github.com/imranp/kerf/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "REPLACE_WITH_RELEASE_TARBALL_SHA256"
  license "MIT"
  head "https://github.com/imranp/kerf.git", branch: "main"

  depends_on "node" => :build
  depends_on "python@3.12"
  depends_on "postgresql@16"

  def install
    # Build the embedded frontend.
    system "npm", "install"
    system "npm", "run", "build:web"

    # Set up Python virtualenv and install dependencies.
    python3 = Formula["python@3.12"].opt_bin/"python3.12"
    system python3, "-m", "venv", libexec/"venv"
    system libexec/"venv/bin/pip", "install", "-r", "backend/requirements.txt"

    # Copy backend source into libexec.
    cp_r "backend", libexec/"backend"

    # Install wrapper script.
    (bin/"kerf").write <<~EOS
      #!/bin/bash
      export PYTHONPATH="#{libexec}/backend"
      exec "#{libexec}/venv/bin/uvicorn" main:app --host 0.0.0.0 --port "${KERF_PORT:-8080}" "$@"
    EOS
    chmod 0755, bin/"kerf"

    pkgshare.install "kerf.example.toml"
  end

  def post_install
    config_dir = "#{Dir.home}/.config/kerf"
    config_file = "#{config_dir}/config.toml"
    return if File.exist?(config_file)

    require "fileutils"
    FileUtils.mkdir_p(config_dir)
    FileUtils.cp("#{pkgshare}/kerf.example.toml", config_file)
    ohai "Wrote default config to #{config_file}"
    ohai "Edit it (set [auth].optional = true for single-user mode), then:"
    ohai "  createdb kerf && kerf"
  end

  service do
    run [opt_bin/"kerf"]
    keep_alive true
    log_path var/"log/kerf.log"
    error_log_path var/"log/kerf.err"
  end

  test do
    assert_predicate bin/"kerf", :exist?
  end
end
