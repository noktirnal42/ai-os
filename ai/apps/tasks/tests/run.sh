#!/bin/sh
set -e
export AIOS_TASKS_FILE="/tmp/tasks_test.json"
rm -f "$AIOS_TASKS_FILE"

# Test add
ID1=$(/ai/bin/tasks add "Task 1")
if [ "$ID1" != "1" ]; then echo "Add 1 failed"; exit 1; fi
ID2=$(/ai/bin/tasks add "Task 2")
if [ "$ID2" != "2" ]; then echo "Add 2 failed"; exit 1; fi

# Test list
LIST=$(/ai/bin/tasks list)
if ! echo "$LIST" | grep -q "1 pending Task 1" || ! echo "$LIST" | grep -q "2 pending Task 2"; then
    echo "List failed"
    exit 1
fi

# Test next
NEXT=$(/ai/bin/tasks next)
if [ "$NEXT" != "1 Task 1" ]; then echo "Next 1 failed: $NEXT"; exit 1; fi

# Test done 1
/ai/bin/tasks done 1
NEXT=$(/ai/bin/tasks next)
if [ "$NEXT" != "2 Task 2" ]; then echo "Next 2 failed: $NEXT"; exit 1; fi

# Test depends
/ai/bin/tasks add "Task 3" --depends 2
NEXT=$(/ai/bin/tasks next)
if [ "$NEXT" != "2 Task 2" ]; then echo "Next should be 2: $NEXT"; exit 1; fi

/ai/bin/tasks done 2
NEXT=$(/ai/bin/tasks next)
if [ "$NEXT" != "3 Task 3" ]; then echo "Next should be 3: $NEXT"; exit 1; fi

# Test fail unknown id
if /ai/bin/tasks fail 999; then
    echo "Fail unknown id should have exited 1"
    exit 1
fi

rm -f "$AIOS_TASKS_FILE"
echo "TASKS_ALL_PASS"
