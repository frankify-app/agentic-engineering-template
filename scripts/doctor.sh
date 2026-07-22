#!/usr/bin/env bash
# Host-tool checks for agentic-engineering repos.
# Default: report only. --install / --fix: bootstrap missing host CLIs (never project deps).
set -euo pipefail

INSTALL=false
if [[ "${1:-}" == "--install" || "${1:-}" == "--fix" ]]; then
    INSTALL=true
fi

# Required host tools for this generated project.
REQUIRED_TOOLS=(git npx uvx gh)
REQUIRED_TOOLS+=(prek)

pass=0
fail=0

check_tool() {
    local tool=$1
    if command -v "$tool" >/dev/null 2>&1; then
        echo "✓ $tool"
        pass=$((pass + 1))
        return 0
    fi
    echo "✗ $tool"
    fail=$((fail + 1))
    return 1
}

warn_tool() {
    local tool=$1
    local message=$2
    if command -v "$tool" >/dev/null 2>&1; then
        echo "✓ $tool"
        pass=$((pass + 1))
    else
        echo "⚠ $tool — $message"
    fi
}

detect_pkg_manager() {
    if [[ "$(uname -s)" == "Darwin" ]] && command -v brew >/dev/null 2>&1; then
        echo brew
    elif command -v apt-get >/dev/null 2>&1; then
        echo apt
    elif command -v apt >/dev/null 2>&1; then
        echo apt
    else
        echo unknown
    fi
}

manual_install_hint() {
    local tool=$1
    case "$tool" in
        git) echo "Install git via your platform package manager." ;;
        gh) echo "brew install gh  OR  sudo apt-get install -y gh" ;;
        npx) echo "brew install node  OR  sudo apt-get install -y npm" ;;
        uvx) echo "brew install uv  OR  curl -LsSf https://astral.sh/uv/install.sh | sh" ;;
        prek) echo "brew install prek  OR  see https://github.com/j178/prek#installation" ;;
        *) echo "Install $tool manually." ;;
    esac
}

install_tool() {
    local tool=$1
    local mgr
    mgr=$(detect_pkg_manager)

    if [[ "$mgr" == unknown ]]; then
        echo "Cannot auto-install $tool: unrecognized platform or package manager."
        manual_install_hint "$tool"
        return 1
    fi

    case "$tool" in
        git)
            case "$mgr" in
                brew) brew install git ;;
                apt) sudo apt-get install -y git ;;
            esac
            ;;
        gh)
            case "$mgr" in
                brew) brew install gh ;;
                apt) sudo apt-get install -y gh ;;
            esac
            ;;
        npx)
            case "$mgr" in
                brew) brew install node ;;
                apt) sudo apt-get install -y npm ;;
            esac
            ;;
        uvx)
            case "$mgr" in
                brew) brew install uv ;;
                apt) curl -LsSf https://astral.sh/uv/install.sh | sh ;;
            esac
            ;;
        prek)
            case "$mgr" in
                brew) brew install prek ;;
                apt)
                    echo "Cannot auto-install prek via apt."
                    manual_install_hint prek
                    return 1
                    ;;
            esac
            ;;
        *)
            echo "No install recipe for $tool."
            return 1
            ;;
    esac
}

echo "agentic doctor — host tool check"
echo

missing=()
for tool in "${REQUIRED_TOOLS[@]}"; do
    if ! check_tool "$tool"; then
        missing+=("$tool")
    fi
done

warn_tool ghx "not installed (deferred; agents use ghx for repo interaction)"


# Decision-memory contract (tools/record.py + grilling skill): warn when the env var is unset;
# when set, a cheap ls-remote surfaces bad URLs / missing credentials now
# instead of mid-session. No clone here — session-start shallow-clone is the
# recorder's job, per-session and ephemeral by design.
decision_memory_failed=false
echo
if [[ -z "${DECISION_MEMORY_URL:-}" ]]; then
    echo "⚠ DECISION_MEMORY_URL — unset; grilling skill skips decision recording. Set it (full git URL) in your shell profile (local), the environment config (remote sessions), or a CI secret."
elif GIT_TERMINAL_PROMPT=0 git ls-remote "$DECISION_MEMORY_URL" >/dev/null 2>&1; then
    echo "✓ DECISION_MEMORY_URL (reachable)"
    pass=$((pass + 1))
else
    echo "✗ DECISION_MEMORY_URL — set but not reachable (bad URL or missing credentials): git ls-remote failed"
    fail=$((fail + 1))
    decision_memory_failed=true
fi

echo
echo "Summary: $pass ok, $fail failed"

if [[ ${#missing[@]} -eq 0 ]]; then
    if [[ "$decision_memory_failed" == true ]]; then
        exit 1
    fi
    exit 0
fi

if [[ "$INSTALL" != true ]]; then
    echo
    echo "Re-run with --install to bootstrap missing host tools."
    for tool in "${missing[@]}"; do
        manual_install_hint "$tool"
    done
    exit 1
fi

echo
echo "Installing missing tools..."
install_failed=false
for tool in "${missing[@]}"; do
    if ! install_tool "$tool"; then
        install_failed=true
    fi
done

if [[ "$install_failed" == true ]]; then
    exit 1
fi

echo
echo "Re-checking..."
exec "$0"

