#!/bin/bash
set -e

ZONE_FILE="/home/bryan/github/aws-dns-crossplane-poc/gitops/poc/arthurbryan.dev.br.yaml"
ACTION="${1}"
AMOUNT="${2}"

# Validate arguments
if [[ -z "$ACTION" ]] || [[ -z "$AMOUNT" ]]; then
    echo "Usage: $0 <create|delete> <amount>"
    echo "Example: $0 create 20"
    echo "Example: $0 delete 20"
    exit 1
fi

if ! [[ "$AMOUNT" =~ ^[0-9]+$ ]]; then
    echo "Error: Amount must be a positive integer"
    exit 1
fi

# Backup original file
cp "$ZONE_FILE" "${ZONE_FILE}.backup"
echo "Backup created: ${ZONE_FILE}.backup"

case "$ACTION" in
    create)
        echo "Creating $AMOUNT test records..."

        # Find existing test record count to continue numbering
        EXISTING_COUNT=$(grep -c "name: test-record-" "$ZONE_FILE" 2>/dev/null || echo "0")
        EXISTING_COUNT=$(echo "$EXISTING_COUNT" | head -1 | tr -d '[:space:]')
        START_NUM=$((EXISTING_COUNT + 1))

        # Create records to append
        TEMP_RECORDS=$(mktemp)

        for i in $(seq "$START_NUM" $((START_NUM + AMOUNT - 1))); do
            # Generate random IP in 10.0.0.0/8 range
            IP="10.$((RANDOM % 256)).$((RANDOM % 256)).$((RANDOM % 256))"

            cat >> "$TEMP_RECORDS" <<EOF

    # Test record $i
    - name: test-record-$i.arthurbryan.dev.br
      type: A
      ttl: 300
      values:
        - "$IP"
EOF
        done

        # Append new records at the end of the records array
        cat "$TEMP_RECORDS" >> "$ZONE_FILE"
        rm "$TEMP_RECORDS"

        echo "Successfully created $AMOUNT test records in $ZONE_FILE"
        ;;

    delete)
        echo "Deleting last $AMOUNT test records..."

        # Count total test records
        TOTAL_TEST_RECORDS=$(grep -c "# Test record" "$ZONE_FILE" 2>/dev/null || echo "0")
        TOTAL_TEST_RECORDS=$(echo "$TOTAL_TEST_RECORDS" | head -1 | tr -d '[:space:]')

        if [[ "$TOTAL_TEST_RECORDS" -eq 0 ]]; then
            echo "No test records found to delete"
            rm "${ZONE_FILE}.backup"
            exit 0
        fi

        if [[ "$AMOUNT" -gt "$TOTAL_TEST_RECORDS" ]]; then
            echo "Warning: Only $TOTAL_TEST_RECORDS test records exist. Deleting all of them."
            AMOUNT=$TOTAL_TEST_RECORDS
        fi

        # Each test record block is 7 lines:
        # (blank line, comment, name, type, ttl, values header, IP value)
        LINES_PER_RECORD=7

        # Calculate how many lines to remove from the end
        LINES_TO_REMOVE=$((AMOUNT * LINES_PER_RECORD))

        # Use head to keep all but last N*7 lines
        TOTAL_LINES=$(wc -l < "$ZONE_FILE")
        LINES_TO_KEEP=$((TOTAL_LINES - LINES_TO_REMOVE))

        if [[ "$LINES_TO_KEEP" -lt 1 ]]; then
            echo "Error: Would remove entire file. Aborting."
            exit 1
        fi

        head -n "$LINES_TO_KEEP" "$ZONE_FILE" > "${ZONE_FILE}.tmp"
        mv "${ZONE_FILE}.tmp" "$ZONE_FILE"

        echo "Successfully deleted $AMOUNT test records from $ZONE_FILE"
        ;;

    *)
        echo "Error: Invalid action '$ACTION'. Use 'create' or 'delete'"
        rm "${ZONE_FILE}.backup"
        exit 1
        ;;
esac

echo ""
CURRENT_COUNT=$(grep -c "# Test record" "$ZONE_FILE" 2>/dev/null || echo "0")
CURRENT_COUNT=$(echo "$CURRENT_COUNT" | head -1 | tr -d '[:space:]')
echo "Current test record count: $CURRENT_COUNT"
echo ""
echo "Next steps:"
echo "  cd /home/bryan/github/aws-dns-crossplane-poc"
echo "  git add gitops/poc/arthurbryan.dev.br.yaml"
echo "  git commit -m 'Test: $ACTION $AMOUNT DNS records'"
echo "  git push"
echo ""
echo "To restore original: mv ${ZONE_FILE}.backup $ZONE_FILE"
