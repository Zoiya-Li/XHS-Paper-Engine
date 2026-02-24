#!/bin/bash
#
# XHS Paper Engine Scheduled Task Installation Script
#
# Usage:
#   ./setup_schedule.sh install    # Install scheduled tasks
#   ./setup_schedule.sh uninstall  # Uninstall scheduled tasks
#   ./setup_schedule.sh status     # View status
#   ./setup_schedule.sh run        # Run immediately once
#

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Project directory
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAUNCHD_DIR="$PROJECT_DIR/launchd"
USER_AGENTS_DIR="$HOME/Library/LaunchAgents"
PYTHON_BIN="${XHS_PAPER_ENGINE_PYTHON:-${DAILYPAPER_PYTHON:-python3}}"

# plist files
MORNING_PLIST="com.xhs-paper-engine.morning.plist"
AFTERNOON_PLIST="com.xhs-paper-engine.afternoon.plist"

echo "========================================"
echo "🚀 XHS Paper Engine Scheduled Task Management"
echo "========================================"
echo "Project Directory: $PROJECT_DIR"
echo ""

install_schedules() {
    echo -e "${YELLOW}📦 Installing scheduled tasks...${NC}"

    # Ensure directories exist
    mkdir -p "$USER_AGENTS_DIR"
    mkdir -p "$PROJECT_DIR/logs"

    # Render plist templates with current paths
    for plist in "$MORNING_PLIST" "$AFTERNOON_PLIST"; do
        sed \
          -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" \
          -e "s|__HOME_DIR__|$HOME|g" \
          "$LAUNCHD_DIR/$plist" > "$USER_AGENTS_DIR/$plist"
    done

    # Load tasks
    launchctl load "$USER_AGENTS_DIR/$MORNING_PLIST" 2>/dev/null
    launchctl load "$USER_AGENTS_DIR/$AFTERNOON_PLIST" 2>/dev/null

    echo -e "${GREEN}✅ Scheduled tasks installed${NC}"
    echo ""
    echo "📅 Schedule:"
    echo "   - Daily at 6:00 AM"
    echo "   - Daily at 6:00 PM (18:00)"
    echo ""
    echo "📝 Log location: $PROJECT_DIR/logs/"
    echo ""

    show_status
}

uninstall_schedules() {
    echo -e "${YELLOW}🗑️  Uninstalling scheduled tasks...${NC}"

    # Unload tasks
    launchctl unload "$USER_AGENTS_DIR/$MORNING_PLIST" 2>/dev/null
    launchctl unload "$USER_AGENTS_DIR/$AFTERNOON_PLIST" 2>/dev/null

    # Remove plist files
    rm -f "$USER_AGENTS_DIR/$MORNING_PLIST"
    rm -f "$USER_AGENTS_DIR/$AFTERNOON_PLIST"

    echo -e "${GREEN}✅ Scheduled tasks uninstalled${NC}"
}

show_status() {
    echo -e "${YELLOW}📊 Scheduled task status:${NC}"
    echo ""

    # Check morning task
    if launchctl list | grep -q "com.xhs-paper-engine.morning"; then
        echo -e "  6:00 AM: ${GREEN}✓ Enabled${NC}"
    else
        echo -e "  6:00 AM: ${RED}✗ Not enabled${NC}"
    fi

    # Check afternoon task
    if launchctl list | grep -q "com.xhs-paper-engine.afternoon"; then
        echo -e "  6:00 PM: ${GREEN}✓ Enabled${NC}"
    else
        echo -e "  6:00 PM: ${RED}✗ Not enabled${NC}"
    fi

    echo ""

    # Show recent run history
    HISTORY_FILE="$PROJECT_DIR/logs/run_history.json"
    if [ -f "$HISTORY_FILE" ]; then
        echo "📜 Recent run history:"
        "$PYTHON_BIN" -c "
import json
with open('$HISTORY_FILE') as f:
    history = json.load(f)
for h in history[-5:]:
    status = '✅' if h['success'] else '❌'
    print(f\"  {status} {h['timestamp'][:19]} ({h['duration_seconds']:.0f}s)\")
" 2>/dev/null || echo "  (Unable to read history)"
    fi
}

run_now() {
    echo -e "${YELLOW}🏃 Running immediately...${NC}"
    echo ""

    cd "$PROJECT_DIR"
    "$PYTHON_BIN" auto_run.py --recent-days 5
}

test_env() {
    echo -e "${YELLOW}🔍 Testing runtime environment...${NC}"
    echo ""

    cd "$PROJECT_DIR"
    "$PYTHON_BIN" auto_run.py --dry-run
}

# Main logic
case "$1" in
    install)
        install_schedules
        ;;
    uninstall)
        uninstall_schedules
        ;;
    status)
        show_status
        ;;
    run)
        run_now
        ;;
    test)
        test_env
        ;;
    *)
        echo "Usage: $0 {install|uninstall|status|run|test}"
        echo ""
        echo "Commands:"
        echo "  install   - Install scheduled tasks (daily at 6:00 and 18:00)"
        echo "  uninstall - Uninstall scheduled tasks"
        echo "  status    - View task status and run history"
        echo "  run       - Run immediately once"
        echo "  test      - Test runtime environment (dry run)"
        exit 1
        ;;
esac

echo ""
echo "========================================"
