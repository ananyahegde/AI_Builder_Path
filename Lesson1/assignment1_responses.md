## AppDev — Code Generation

**Prompt 1:**
Write a Python function that takes a list of user dictionaries (each with "name", "email", "signup_date") and returns only users who signed up in the last 30 days, sorted by signup_date descending. Handle missing/malformed dates gracefully.

**Prompt 2:**
Refactor this function to be thread-safe and add proper error handling with logging:

```python
def process_queue(queue):
    results = []
    while queue:
        item = queue.pop()
        results.append(item * 2)
    return results
```

Explain what race conditions existed in the original version.

## Data — SQL Generation

**Prompt 1:**
Given two tables — orders(order_id, customer_id, order_date, amount) and customers(customer_id, name, region) — write a SQL query to find the top 3 customers by total order amount in each region, using a window function.

**Prompt 2:**
Write a SQL query to detect customers who placed orders in Q1 but had zero orders in Q2 of the same year (churn detection). Use the same orders/customers schema as above. Then explain how you'd optimize this query if the orders table has 50M+ rows.

## DevOps — Infrastructure Automation

**Prompt 1:**
Write a Terraform config to provision an AWS S3 bucket with versioning enabled, server-side encryption, and a bucket policy that blocks all public access.

**Prompt 2:**
Write a GitHub Actions workflow YAML that builds a Docker image, runs unit tests, and only pushes to a container registry if tests pass and the branch is "main". Include caching for dependencies to speed up builds.

---

## Claude

https://claude.ai/share/e3f8f71d-be1c-46d4-a35b-15f58cafc452

### AppDev — Code Generation

**Prompt 1: Recent Signups Filter**

```python
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

def get_recent_signups(users, days=30, reference_date=None):
    """
    Return users who signed up within the last `days` days, sorted by
    signup_date descending. Entries with missing/malformed dates are
    skipped (and logged) rather than raising.

    Args:
        users: list of dicts with "name", "email", "signup_date" (ISO format string, e.g. "2026-06-15")
        days: lookback window in days
        reference_date: datetime to compare against (defaults to now); useful for testing

    Returns:
        list of user dicts, sorted newest-first
    """
    now = reference_date or datetime.now()
    cutoff = now - timedelta(days=days)

    valid_users = []
    for user in users:
        raw_date = user.get("signup_date")
        if not raw_date:
            logger.warning("Skipping user with missing signup_date: %s", user.get("email", "<no email>"))
            continue

        parsed_date = _parse_date(raw_date)
        if parsed_date is None:
            logger.warning("Skipping user with malformed signup_date '%s': %s", raw_date, user.get("email", "<no email>"))
            continue

        if parsed_date >= cutoff:
            valid_users.append((parsed_date, user))

    valid_users.sort(key=lambda pair: pair[0], reverse=True)
    return [user for _, user in valid_users]


def _parse_date(raw_date):
    """Try a few common formats; return None if none work."""
    if isinstance(raw_date, datetime):
        return raw_date

    formats = ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d", "%m/%d/%Y")
    for fmt in formats:
        try:
            return datetime.strptime(raw_date, fmt)
        except (ValueError, TypeError):
            continue
    return None
```

Key design choices: malformed/missing entries are logged and skipped rather than crashing the whole batch; reference_date is injectable for deterministic unit tests; sorting happens on parsed datetime objects, not strings, to avoid lexicographic-sort bugs across formats.

**Prompt 2: Thread-Safe Queue Processor**

```python
import threading
import logging

logger = logging.getLogger(__name__)

def process_queue(queue, lock=None):
    """
    Thread-safe version: pops items under a lock, processes them
    outside the lock (to avoid holding it during potentially slow work),
    and tolerates errors on individual items without losing the rest.
    """
    lock = lock or threading.Lock()
    results = []

    while True:
        with lock:
            if not queue:
                break
            item = queue.pop()

        try:
            results.append(item * 2)
        except TypeError as e:
            logger.error("Failed to process item %r: %s", item, e)
            continue

    return results
```

Race conditions in the original:

1. Check-then-act on `while queue` — Between checking if queue (implicit in `while queue`) and calling `queue.pop()`, another thread could pop the last element. If queue were shared across threads calling this function concurrently, pop() could raise IndexError on an empty list, or two threads could think there's exactly one item left and both try to take it.
2. Non-atomic pop() + append() pair — Even though Python's GIL makes individual list operations atomic, the sequence of "pop from queue" then "append to results" is not atomic as a unit. Interleaving between threads could cause results to be appended out of sync with what was actually popped (matters more if results were shared, or if processing had side effects depending on order).
3. No isolation between threads sharing queue — If two threads both call process_queue(queue) on the same queue object, they'd race on pop(), silently splitting work in a non-deterministic and unrepeatable way, with no guarantee each thread gets a complete or consistent partition.
4. No error containment — A single bad item (e.g., a string where multiplication behaves unexpectedly, or a None) would let a TypeError propagate and kill the whole batch, losing all previously accumulated results for that thread.

The fix wraps the check-and-pop as one atomic action inside the lock, keeps the lock's critical section as small as possible (just the mutation of shared state), and isolates per-item errors so one bad element doesn't nuke the whole run.

### Data — SQL Generation

**Prompt 1: Top 3 Customers per Region**

```sql
WITH customer_totals AS (
    SELECT
        c.customer_id,
        c.name,
        c.region,
        SUM(o.amount) AS total_amount
    FROM customers c
    JOIN orders o ON o.customer_id = c.customer_id
    GROUP BY c.customer_id, c.name, c.region
),
ranked AS (
    SELECT
        customer_id,
        name,
        region,
        total_amount,
        RANK() OVER (PARTITION BY region ORDER BY total_amount DESC) AS region_rank
    FROM customer_totals
)
SELECT customer_id, name, region, total_amount, region_rank
FROM ranked
WHERE region_rank <= 3
ORDER BY region, region_rank;
```

Notes: RANK() handles ties by giving equal amounts the same rank (so you might get more than 3 rows per region on a tie) — swap to ROW_NUMBER() if you need exactly 3 rows per region regardless of ties, or DENSE_RANK() if you want tie-aware ranking without rank gaps.

**Prompt 2: Q1→Q2 Churn Detection**

```sql
WITH q1_customers AS (
    SELECT DISTINCT c.customer_id
    FROM customers c
    JOIN orders o ON o.customer_id = c.customer_id
    WHERE o.order_date >= DATE '2026-01-01'
      AND o.order_date <  DATE '2026-04-01'
),
q2_customers AS (
    SELECT DISTINCT c.customer_id
    FROM customers c
    JOIN orders o ON o.customer_id = c.customer_id
    WHERE o.order_date >= DATE '2026-04-01'
      AND o.order_date <  DATE '2026-07-01'
)
SELECT c.customer_id, c.name, c.region
FROM customers c
JOIN q1_customers q1 ON q1.customer_id = c.customer_id
LEFT JOIN q2_customers q2 ON q2.customer_id = c.customer_id
WHERE q2.customer_id IS NULL;
```

(Swap the hardcoded 2026 boundaries for a parameter or a DATE_TRUNC-based dynamic range if you want this to run for "any year".)

Optimizing at 50M+ rows:

* Index orders(customer_id, order_date) as a composite — this lets both the Q1 and Q2 CTEs satisfy their date-range filter and the join on customer_id from a single index scan instead of a full table scan.
* Partition the orders table by order_date (range partitioning, e.g. monthly or quarterly). This lets the query planner prune partitions outside Q1/Q2 entirely rather than scanning all 50M rows.
* Avoid DISTINCT over the whole join where possible — an EXISTS/NOT EXISTS formulation often outperforms DISTINCT + LEFT JOIN ... IS NULL because it can short-circuit per customer instead of materializing full match sets:

```sql
SELECT c.customer_id, c.name, c.region
FROM customers c
WHERE EXISTS (
    SELECT 1 FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.order_date >= DATE '2026-01-01' AND o.order_date < DATE '2026-04-01'
)
AND NOT EXISTS (
    SELECT 1 FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.order_date >= DATE '2026-04-01' AND o.order_date < DATE '2026-07-01'
);
```

* Pre-aggregate into a materialized summary table (e.g., customer_quarterly_activity(customer_id, year, quarter, order_count)) refreshed nightly, if this churn check runs frequently — turns a 50M-row scan into a lookup against a much smaller table.
* Check the query plan (EXPLAIN ANALYZE) to confirm the planner is actually using the index/partition pruning rather than falling back to sequential scans, especially after large data loads where statistics may be stale (ANALYZE orders).

### DevOps — Infrastructure Automation

**Prompt 1: S3 Bucket (Terraform)**

```hcl
resource "aws_s3_bucket" "this" {
  bucket = var.bucket_name

  tags = {
    Name        = var.bucket_name
    Environment = var.environment
  }
}

resource "aws_s3_bucket_versioning" "this" {
  bucket = aws_s3_bucket.this.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.this.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  bucket = aws_s3_bucket.this.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "deny_insecure_transport" {
  bucket = aws_s3_bucket.this.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.this.arn,
          "${aws_s3_bucket.this.arn}/*"
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      }
    ]
  })

  depends_on = [aws_s3_bucket_public_access_block.this]
}

variable "bucket_name" {
  type = string
}

variable "environment" {
  type    = string
  default = "production"
}
```

Notes: aws_s3_bucket_public_access_block is the actual mechanism that "blocks all public access" (all four flags set true); the bucket policy here additionally denies non-HTTPS requests, which is a common companion hardening step — remove it if you only wanted the public-access block. Swap sse_algorithm to "AES256" if you don't want to manage a KMS key.

**Prompt 2: GitHub Actions CI/CD Workflow**

```yaml
name: Build, Test, and Push

on:
  push:
    branches: ["**"]
  pull_request:
    branches: ["main"]

env:
  IMAGE_NAME: ghcr.io/${{ github.repository }}

jobs:
  build-and-test:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Cache Docker layers
        uses: actions/cache@v4
        with:
          path: /tmp/.buildx-cache
          key: ${{ runner.os }}-buildx-${{ github.sha }}
          restore-keys: |
            ${{ runner.os }}-buildx-

      - name: Build image (for testing)
        uses: docker/build-push-action@v5
        with:
          context: .
          load: true
          tags: ${{ env.IMAGE_NAME }}:test
          cache-from: type=local,src=/tmp/.buildx-cache
          cache-to: type=local,dest=/tmp/.buildx-cache-new,mode=max

      - name: Run unit tests
        run: |
          docker run --rm ${{ env.IMAGE_NAME }}:test \
            sh -c "pytest --maxfail=1 --disable-warnings -q"

      - name: Move cache
        run: |
          rm -rf /tmp/.buildx-cache
          mv /tmp/.buildx-cache-new /tmp/.buildx-cache

      - name: Log in to GitHub Container Registry
        if: github.ref == 'refs/heads/main' && github.event_name == 'push'
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Push image
        if: github.ref == 'refs/heads/main' && github.event_name == 'push'
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ${{ env.IMAGE_NAME }}:latest
            ${{ env.IMAGE_NAME }}:${{ github.sha }}
          cache-from: type=local,src=/tmp/.buildx-cache
          cache-to: type=local,dest=/tmp/.buildx-cache,mode=max
```

Notes: tests run against the built image itself (docker run ... pytest), so "tests pass" gates the push job's `if` conditions along with the branch check — a failed Run unit tests step halts the workflow before the login/push steps execute. Layer caching uses GitHub Actions cache (actions/cache) with buildx's local cache exporter, which is the standard low-friction approach; for larger projects, registry-based caching (type=registry) scales better across runners. Adjust the pytest invocation and base image assumptions to match your actual test runner and Dockerfile structure.

---

## ChatGPT

https://chatgpt.com/share/6a451c2a-8f50-83e8-a2cf-9271e9033228

### Lesson 1

### AppDev — Code Generation

**Prompt 1**

```python
from datetime import datetime, timedelta
from typing import List, Dict

def recent_users(users: List[Dict]) -> List[Dict]:
    """
    Returns users who signed up within the last 30 days,
    sorted by signup_date descending.

    Handles missing or malformed dates by skipping those records.
    """

    cutoff = datetime.now() - timedelta(days=30)
    valid_users = []

    for user in users:
        date_str = user.get("signup_date")

        if not date_str:
            continue

        try:
            # Supports YYYY-MM-DD or full ISO timestamps
            signup_date = datetime.fromisoformat(date_str)
        except (ValueError, TypeError):
            continue

        if signup_date >= cutoff:
            valid_users.append((signup_date, user))

    valid_users.sort(key=lambda x: x[0], reverse=True)

    return [user for _, user in valid_users]
```

Example

```python
users = [
    {
        "name": "Alice",
        "email": "alice@example.com",
        "signup_date": "2026-06-15"
    },
    {
        "name": "Bob",
        "email": "bob@example.com",
        "signup_date": "invalid-date"
    },
    {
        "name": "Charlie",
        "email": "charlie@example.com",
        "signup_date": "2026-05-10"
    }
]

print(recent_users(users))
```

**Prompt 2**

```python
import logging
from queue import Queue, Empty

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def process_queue(work_queue: Queue):
    """
    Thread-safe queue processing.
    """

    results = []

    while True:
        try:
            item = work_queue.get_nowait()
        except Empty:
            break

        try:
            results.append(item * 2)
        except Exception as e:
            logger.exception("Failed processing item %r: %s", item, e)
        finally:
            work_queue.task_done()

    return results
```

If a shared list must be used

```python
import threading
import logging

logger = logging.getLogger(__name__)

queue_lock = threading.Lock()

def process_queue(queue):
    results = []

    while True:
        with queue_lock:
            if not queue:
                break
            item = queue.pop()

        try:
            results.append(item * 2)
        except Exception:
            logger.exception("Error processing item %r", item)

    return results
```

Race conditions in the original version

The original implementation:

```python
def process_queue(queue):
    results = []
    while queue:
        item = queue.pop()
        results.append(item * 2)
    return results
```

Problems:

1. Check-then-act race
    * One thread checks `while queue`.
    * Before `queue.pop()` executes, another thread empties the queue.
    * The first thread then raises IndexError.
2. Unsynchronized mutation
    * Multiple threads modify the same list simultaneously.
    * List operations are not intended as a producer/consumer synchronization mechanism.
3. Lost or duplicated work
    * Items may be processed unpredictably depending on thread scheduling.
4. No error handling
    * One bad item terminates processing.
5. No logging
    * Failures are difficult to diagnose.

Using queue.Queue is the preferred solution because it is designed to be thread-safe.

### Data — SQL Generation

**Prompt 1**

```sql
WITH customer_totals AS (
    SELECT
        c.region,
        c.customer_id,
        c.name,
        SUM(o.amount) AS total_amount
    FROM customers c
    JOIN orders o
        ON c.customer_id = o.customer_id
    GROUP BY
        c.region,
        c.customer_id,
        c.name
),
ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY region
            ORDER BY total_amount DESC
        ) AS rn
    FROM customer_totals
)
SELECT
    region,
    customer_id,
    name,
    total_amount
FROM ranked
WHERE rn <= 3
ORDER BY region, total_amount DESC;
```

**Prompt 2**

```sql
WITH q1_customers AS (
    SELECT DISTINCT
        customer_id,
        EXTRACT(YEAR FROM order_date) AS order_year
    FROM orders
    WHERE EXTRACT(QUARTER FROM order_date) = 1
),
q2_customers AS (
    SELECT DISTINCT
        customer_id,
        EXTRACT(YEAR FROM order_date) AS order_year
    FROM orders
    WHERE EXTRACT(QUARTER FROM order_date) = 2
)
SELECT
    c.customer_id,
    c.name,
    c.region,
    q1.order_year
FROM q1_customers q1
JOIN customers c
    ON c.customer_id = q1.customer_id
LEFT JOIN q2_customers q2
    ON q1.customer_id = q2.customer_id
   AND q1.order_year = q2.order_year
WHERE q2.customer_id IS NULL
ORDER BY q1.order_year, c.customer_id;
```

Optimizing for 50M+ rows

1. Create a composite index:

```sql
CREATE INDEX idx_orders_customer_date
ON orders(customer_id, order_date);
```

2. Partition the table by order_date (monthly or yearly).
3. Avoid repeated EXTRACT() on every row by using date ranges:

```sql
WHERE order_date >= '2026-01-01'
  AND order_date < '2026-04-01'
```

instead of

```sql
EXTRACT(QUARTER FROM order_date) = 1
```

4. Maintain summary/materialized tables for quarterly customer activity.
5. Use NOT EXISTS instead of LEFT JOIN ... IS NULL where the optimizer performs better:

```sql
SELECT DISTINCT o1.customer_id
FROM orders o1
WHERE o1.order_date >= DATE '2026-01-01'
  AND o1.order_date < DATE '2026-04-01'
  AND NOT EXISTS (
      SELECT 1
      FROM orders o2
      WHERE o2.customer_id = o1.customer_id
        AND o2.order_date >= DATE '2026-04-01'
        AND o2.order_date < DATE '2026-07-01'
  );
```

### DevOps — Infrastructure Automation

**Prompt 1 (Terraform)**

```hcl
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

resource "aws_s3_bucket" "secure_bucket" {
  bucket = "my-secure-demo-bucket-12345"
}

resource "aws_s3_bucket_versioning" "versioning" {
  bucket = aws_s3_bucket.secure_bucket.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "encryption" {
  bucket = aws_s3_bucket.secure_bucket.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "public_block" {
  bucket = aws_s3_bucket.secure_bucket.id

  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "bucket_policy" {
  bucket = aws_s3_bucket.secure_bucket.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.secure_bucket.arn,
          "${aws_s3_bucket.secure_bucket.arn}/*"
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      }
    ]
  })
}
```

**Prompt 2 (GitHub Actions)**

```yaml
name: CI

on:
  push:
    branches:
      - "**"
  pull_request:

jobs:
  build-test:
    runs-on: ubuntu-latest

    outputs:
      image_tag: ${{ steps.meta.outputs.tag }}

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
      uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"

      - name: Install dependencies
        run: |
          pip install -r requirements.txt

      - name: Run unit tests
        run: |
          pytest

      - name: Set image tag
        id: meta
        run: echo "tag=${GITHUB_SHA}" >> $GITHUB_OUTPUT

      - name: Build Docker image
        run: |
          docker build -t myapp:${GITHUB_SHA} .

  push-image:
    needs: build-test
    if: github.ref == 'refs/heads/main'

    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and Push
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ghcr.io/${{ github.repository }}:${{ needs.build-test.outputs.image_tag }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

This workflow:

* Triggers on pushes and pull requests.
* Installs and caches Python dependencies.
* Runs unit tests before any image push.
* Builds the Docker image.
* Pushes the image only when the workflow succeeds and the branch is main.
* Uses GitHub Actions cache (type=gha) to accelerate Docker builds.

---

## Gemini

https://share.gemini.google/5vILOe1jibKP

Here are the completed exercises for Lesson 1, covering Application Development, Data/SQL, and DevOps.

### AppDev — Code Generation

**Prompt 1: Filter & Sort Users**

This solution uses Python's built-in datetime module. It filters out missing or malformed dates gracefully by catching parsing exceptions and logging/skipping those records.

```python
from datetime import datetime, timedelta, timezone
import logging

# Configure basic logging
logging.basicConfig(level=logging.INFO)

def get_recent_signups(users: list) -> list:
    """
    Filters and returns users who signed up in the last 30 days,
    sorted by signup_date in descending order.
    """
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)
    valid_users = []

    for user in users:
        # Gracefully handle missing dictionary keys or None values
        signup_date_str = user.get("signup_date")
        if not signup_date_str:
            logging.warning(f"Skipping user {user.get('name', 'Unknown')}: Missing signup_date.")
            continue
            
        try:
            # Assumes ISO 8601 format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)
            # fromisoformat handles 'Z' offset directly in Python 3.11+
            signup_date = datetime.fromisoformat(signup_date_str.replace('Z', '+00:00'))
            
            # Ensure naive datetimes are treated as UTC if necessary
            if signup_date.tzinfo is None:
                signup_date = signup_date.replace(tzinfo=timezone.utc)

            if thirty_days_ago <= signup_date <= now:
                # Store the parsed date alongside the user for efficient sorting
                valid_users.append((signup_date, user))
                
        except ValueError as e:
            logging.error(f"Skipping user {user.get('name', 'Unknown')}: Malformed date '{signup_date_str}'. Error: {e}")
            continue

    # Sort by the parsed datetime object (index 0 of the tuple) in descending order
    valid_users.sort(key=lambda x: x[0], reverse=True)
    
    # Extract and return just the user dictionaries
    return [user for _, user in valid_users]
```

**Prompt 2: Thread-Safe Refactoring & Race Conditions**

Refactored Code

```python
import logging
from collections import deque
from threading import Lock

# Setup logging
logger = logging.getLogger(__name__)

# Standard Python lists are not fully thread-safe for pop() under heavy concurrent mutation.
# We use a Lock to guarantee atomicity and thread safety.
queue_lock = Lock()

def process_queue(queue) -> list:
    """
    Thread-safe processing of a shared list or deque.
    """
    results = []
    
    while True:
        item = None
        with queue_lock:
            # Check if elements still exist inside the lock context
            if queue:
                # If it's a standard list, pop() removes from the end. 
                # If it's a collections.deque, pop() or popleft() works similarly.
                item = queue.pop()
            else:
                # Queue is completely empty, break out of the loop safely
                break
        
        # Process the item outside of the lock context to minimize hold time
        try:
            if item is not None:
                results.append(item * 2)
        except TypeError as e:
            logger.error(f"Failed to process item '{item}': Invalid type for multiplication. Error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error processing item '{item}': {e}")
            
    return results
```

Race Conditions in the Original Version

1. The `while queue:` check: In a multi-threaded context, Thread A might pass the `while queue:` check because the list contains 1 item. Before Thread A executes `queue.pop()`, the OS switches contexts to Thread B. Thread B also passes the `while queue:` check, executes `queue.pop()`, and empties the list. When control returns to Thread A, it executes `queue.pop()` on an empty list, throwing an IndexError.
2. Non-Atomic Operations: While individual standard list methods like `pop()` are atomic in CPython due to the Global Interpreter Lock (GIL), combining a read/check (`while queue:`) with a write mutation (`queue.pop()`) is not atomic. This creates a time-of-check to time-of-use (TOCTOU) vulnerability.

### Data — SQL Generation

**Prompt 1: Top 3 Customers by Region (Window Function)**

```sql
WITH ranked_customers AS (
    SELECT 
        c.customer_id,
        c.name AS customer_name,
        c.region,
        SUM(o.amount) AS total_order_amount,
        DENSE_RANK() OVER (
            PARTITION BY c.region 
            ORDER BY SUM(o.amount) DESC
        ) AS region_rank
    FROM customers c
    JOIN orders o ON c.customer_id = o.customer_id
    GROUP BY c.customer_id, c.name, c.region
)
SELECT 
    region,
    customer_id,
    customer_name,
    total_order_amount
FROM ranked_customers
WHERE region_rank <= 3
ORDER BY region, region_rank;
```

**Prompt 2: Q1 vs Q2 Churn Detection & Optimization**

SQL Query

```sql
SELECT DISTINCT
    c.customer_id,
    c.name,
    c.region
FROM customers c
JOIN orders o1 ON c.customer_id = o1.customer_id
WHERE o1.order_date >= '2026-01-01' AND o1.order_date < '2026-04-01' -- Q1 Orders
  AND NOT EXISTS (
      SELECT 1 
      FROM orders o2 
      WHERE o2.customer_id = c.customer_id
        AND o2.order_date >= '2026-04-01' AND o2.order_date < '2026-07-01' -- Q2 Orders
  );
```

Optimization Strategy for 50M+ Rows

* Indexing: Create a composite index on the orders table for (customer_id, order_date). This allows the engine to swiftly evaluate the JOIN predicate and the NOT EXISTS subquery criteria without scanning the whole table.
* Partitioning: Partition the orders table by range or list using the order_date column (e.g., monthly or quarterly partitions). The database engine can utilize partition pruning to scan only the specific partitions holding Q1 and Q2 data, completely skipping the remaining millions of rows.
* Covering Index / Index-Only Scan: If the index on orders includes amount or is structured properly as (order_date, customer_id), the query can execute via an Index-Only Scan, eliminating the need to look up data blocks on physical disk storage.

### DevOps — Infrastructure Automation

**Prompt 1: Secure AWS S3 Bucket (Terraform)**

```hcl
provider "aws" {
  region = "us-east-1"
}

resource "aws_s3_bucket" "secure_bucket" {
  bucket = "my-highly-secure-app-bucket-2026"

  tags = {
    Environment = "Production"
    ManagedBy   = "Terraform"
  }
}

# 1. Enable Versioning
resource "aws_s3_bucket_versioning" "versioning" {
  bucket = aws_s3_bucket.secure_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

# 2. Server-Side Encryption (AES256 default)
resource "aws_s3_bucket_server_side_encryption_configuration" "encryption" {
  bucket = aws_s3_bucket.secure_bucket.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# 3. Block Public Access (Bucket level settings)
resource "aws_s3_bucket_public_access_block" "public_block" {
  bucket = aws_s3_bucket.secure_bucket.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# 4. Explicit Deny Bucket Policy for Non-SSL requests (Ensures encrypted transit)
resource "aws_s3_bucket_policy" "allow_secure_transport_only" {
  bucket = aws_s3_bucket.secure_bucket.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "EnforceTLSRequestsOnly"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.secure_bucket.arn,
          "${aws_s3_bucket.secure_bucket.arn}/*"
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      }
    ]
  })
  
  # Ensure public access blocks are evaluated prior to assigning bucket policy
  depends_on = [aws_s3_bucket_public_access_block.public_block]
}
```

**Prompt 2: CI/CD Pipeline Workflow (GitHub Actions)**

```yaml
name: Build, Test, and Push CI

on:
  push:
    branches: [ "main", "develop" ]
  pull_request:
    branches: [ "main" ]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  build-and-test:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      # Set up Docker Buildx for advanced caching capabilities
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      # Leverage GitHub Actions native caching for Docker layers
      - name: Cache Docker layers
        uses: actions/cache@v4
        with:
          path: /tmp/.buildx-cache
          key: ${{ runner.os }}-buildx-${{ github.sha }}
          restore-keys: |
            ${{ runner.os }}-buildx-

      - name: Build local image for testing
        uses: docker/build-push-action@v5
        with:
          context: .
          load: true # Loads image into local Docker daemon for container testing
          tags: app-test:local
          cache-from: type=local,src=/tmp/.buildx-cache
          cache-to: type=local,dest=/tmp/.buildx-all-new,mode=max

      - name: Run Unit Tests
        run: |
          docker run --rm app-test:local npm test || docker run --rm app-test:local pytest

      # Registry login and conditional push steps run only if tests pass and branch is main
      - name: Log in to the Container Registry
        if: success() && github.ref == 'refs/heads/main'
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract Docker metadata
        if: success() && github.ref == 'refs/heads/main'
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=sha,format=long
            type=ref,event=branch

      # Push to registry
      - name: Push Production Docker Image
        if: success() && github.ref == 'refs/heads/main'
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=local,src=/tmp/.buildx-cache

      # Move cache records to avoid unbounded growth
      - name: Move cache
        run: |
          rm -rf /tmp/.buildx-cache
          mv /tmp/.buildx-all-new /tmp/.buildx-cache
```

---

## Deepseek

https://chat.deepseek.com/share/ws47pke1ulyjugn7y3

# Lesson 1 Solutions

## AppDev — Code Generation

### Prompt 1: User Filtering Function

```python
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def filter_recent_users(users: List[Dict]) -> List[Dict]:
    """
    Filter users who signed up in the last 30 days and sort by signup_date descending.
    
    Args:
        users: List of user dictionaries with "name", "email", "signup_date"
    
    Returns:
        List of filtered and sorted users
    """
    if not users:
        return []
    
    thirty_days_ago = datetime.now() - timedelta(days=30)
    filtered_users = []
    
    for user in users:
        try:
            # Validate required fields exist
            if not all(key in user for key in ["name", "email", "signup_date"]):
                logger.warning(f"Skipping user: missing required fields - {user}")
                continue
            
            # Parse signup_date (handle string or datetime object)
            if isinstance(user["signup_date"], str):
                signup_date = datetime.fromisoformat(user["signup_date"])
            elif isinstance(user["signup_date"], datetime):
                signup_date = user["signup_date"]
            else:
                raise ValueError(f"Unsupported date type: {type(user['signup_date'])}")
            
            # Check if within last 30 days
            if signup_date >= thirty_days_ago:
                filtered_users.append(user)
                
        except (ValueError, TypeError) as e:
            logger.error(f"Error processing user {user.get('email', 'unknown')}: {e}")
            continue
    
    # Sort by signup_date descending
    def get_signup_date(user):
        if isinstance(user["signup_date"], str):
            return datetime.fromisoformat(user["signup_date"])
        return user["signup_date"]
    
    return sorted(filtered_users, key=get_signup_date, reverse=True)
```

### Prompt 2: Thread-Safe Queue Processing

```python
import threading
import logging
from queue import Queue
from typing import List, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ThreadSafeQueueProcessor:
    def __init__(self):
        self._lock = threading.Lock()
        self._processed_items = 0
        self._errors = 0
        
    def process_queue_thread_safe(self, queue: Queue) -> List[Any]:
        """
        Process queue items in a thread-safe manner.
        
        Args:
            queue: A thread-safe Queue object
            
        Returns:
            List of processed results
        """
        results = []
        
        while True:
            try:
                # Non-blocking get with timeout
                item = queue.get(timeout=0.1)
                
                try:
                    # Process item safely
                    if not isinstance(item, (int, float)):
                        raise ValueError(f"Expected number, got {type(item)}")
                    
                    result = item * 2
                    results.append(result)
                    
                    with self._lock:
                        self._processed_items += 1
                    
                    logger.debug(f"Processed item: {item} -> {result}")
                    
                except Exception as e:
                    with self._lock:
                        self._errors += 1
                    logger.error(f"Error processing item {item}: {e}")
                finally:
                    queue.task_done()
                    
            except Exception as e:
                # Queue is empty or timeout occurred
                break
        
        logger.info(f"Processed {self._processed_items} items with {self._errors} errors")
        return results
    
    def get_stats(self):
        """Return processing statistics"""
        with self._lock:
            return {
                "processed": self._processed_items,
                "errors": self._errors
            }

# Alternative simpler thread-safe version using list with lock
def process_queue_thread_safe_simple(queue: list, lock: threading.Lock) -> list:
    """
    Process a list queue in a thread-safe manner.
    
    Args:
        queue: List to process (must be accessed with lock)
        lock: Threading lock object
    
    Returns:
        List of processed results
    """
    results = []
    
    while True:
        with lock:
            if not queue:
                break
            item = queue.pop(0)  # Use pop(0) for FIFO
        
        try:
            if not isinstance(item, (int, float)):
                raise ValueError(f"Expected number, got {type(item)}")
            results.append(item * 2)
        except Exception as e:
            logger.error(f"Error processing item {item}: {e}")
    
    return results
```

**Race Conditions in Original Version:**

1. **Concurrent pop()**: Multiple threads calling `pop()` simultaneously could get the same item or cause index errors
2. **Non-atomic operations**: The check `while queue:` and pop operation are separate steps, allowing race conditions
3. **Data corruption**: Concurrent modifications to the list could corrupt the internal state
4. **Lost updates**: Results list append operations could be interleaved incorrectly

---

## Data — SQL Generation

### Prompt 1: Top 3 Customers by Region Using Window Functions

```sql
WITH customer_totals AS (
    SELECT 
        c.customer_id,
        c.name,
        c.region,
        SUM(o.amount) AS total_order_amount,
        ROW_NUMBER() OVER (
            PARTITION BY c.region 
            ORDER BY SUM(o.amount) DESC
        ) AS rank_in_region
    FROM customers c
    INNER JOIN orders o ON c.customer_id = o.customer_id
    GROUP BY c.customer_id, c.name, c.region
)
SELECT 
    region,
    customer_id,
    name,
    total_order_amount,
    rank_in_region
FROM customer_totals
WHERE rank_in_region <= 3
ORDER BY region, rank_in_region;
```

### Prompt 2: Churn Detection Query

```sql
WITH q1_orders AS (
    SELECT DISTINCT customer_id
    FROM orders
    WHERE EXTRACT(YEAR FROM order_date) = EXTRACT(YEAR FROM CURRENT_DATE)
      AND EXTRACT(QUARTER FROM order_date) = 1
),
q2_orders AS (
    SELECT DISTINCT customer_id
    FROM orders
    WHERE EXTRACT(YEAR FROM order_date) = EXTRACT(YEAR FROM CURRENT_DATE)
      AND EXTRACT(QUARTER FROM order_date) = 2
)
SELECT 
    c.customer_id,
    c.name,
    c.region,
    COALESCE(SUM(o1.amount), 0) AS q1_total,
    COALESCE(SUM(o2.amount), 0) AS q2_total
FROM customers c
INNER JOIN q1_orders q1 ON c.customer_id = q1.customer_id
LEFT JOIN q2_orders q2 ON c.customer_id = q2.customer_id
LEFT JOIN orders o1 ON c.customer_id = o1.customer_id 
    AND EXTRACT(YEAR FROM o1.order_date) = EXTRACT(YEAR FROM CURRENT_DATE)
    AND EXTRACT(QUARTER FROM o1.order_date) = 1
LEFT JOIN orders o2 ON c.customer_id = o2.customer_id 
    AND EXTRACT(YEAR FROM o2.order_date) = EXTRACT(YEAR FROM CURRENT_DATE)
    AND EXTRACT(QUARTER FROM o2.order_date) = 2
WHERE q2.customer_id IS NULL
GROUP BY c.customer_id, c.name, c.region;
```

**Optimization for 50M+ rows:**

1. **Add indexes:**

```sql
CREATE INDEX idx_orders_customer_date ON orders(customer_id, order_date);
CREATE INDEX idx_orders_date_quarter ON orders(order_date) 
    WHERE EXTRACT(YEAR FROM order_date) = EXTRACT(YEAR FROM CURRENT_DATE);
```

2. **Use partitioning:**

```sql
-- Partition by year
CREATE TABLE orders_partitioned (
    order_id INT,
    customer_id INT,
    order_date DATE,
    amount DECIMAL
) PARTITION BY RANGE (EXTRACT(YEAR FROM order_date));

-- Create partitions for each year
CREATE TABLE orders_2024 PARTITION OF orders_partitioned
    FOR VALUES FROM (2024) TO (2025);
```

3. **Use materialized views for pre-aggregated data:**

```sql
CREATE MATERIALIZED VIEW mv_customer_quarterly_stats AS
SELECT 
    customer_id,
    EXTRACT(YEAR FROM order_date) AS year,
    EXTRACT(QUARTER FROM order_date) AS quarter,
    SUM(amount) AS total_amount
FROM orders
GROUP BY customer_id, EXTRACT(YEAR FROM order_date), EXTRACT(QUARTER FROM order_date);

-- Refresh periodically
REFRESH MATERIALIZED VIEW mv_customer_quarterly_stats;
```

4. **Use EXISTS instead of LEFT JOIN for better performance:**

```sql
SELECT c.customer_id, c.name, c.region
FROM customers c
WHERE EXISTS (
    SELECT 1 FROM orders o1
    WHERE o1.customer_id = c.customer_id
    AND EXTRACT(YEAR FROM o1.order_date) = EXTRACT(YEAR FROM CURRENT_DATE)
    AND EXTRACT(QUARTER FROM o1.order_date) = 1
)
AND NOT EXISTS (
    SELECT 1 FROM orders o2
    WHERE o2.customer_id = c.customer_id
    AND EXTRACT(YEAR FROM o2.order_date) = EXTRACT(YEAR FROM CURRENT_DATE)
    AND EXTRACT(QUARTER FROM o2.order_date) = 2
);
```

---

## DevOps — Infrastructure Automation

### Prompt 1: Terraform AWS S3 Configuration

```hcl
# provider.tf
provider "aws" {
  region = var.aws_region
}

# variables.tf
variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "bucket_name" {
  description = "Name of the S3 bucket"
  type        = string
  default     = "my-secure-bucket-${random_id.bucket_suffix.hex}"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production"
}

# random_id.tf
resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# s3_bucket.tf
resource "aws_s3_bucket" "secure_bucket" {
  bucket = var.bucket_name
  tags = {
    Name        = var.bucket_name
    Environment = var.environment
  }
}

# Versioning
resource "aws_s3_bucket_versioning" "bucket_versioning" {
  bucket = aws_s3_bucket.secure_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Server-side encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "bucket_encryption" {
  bucket = aws_s3_bucket.secure_bucket.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Block public access
resource "aws_s3_bucket_public_access_block" "bucket_public_access" {
  bucket = aws_s3_bucket.secure_bucket.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Bucket policy (explicitly deny all public access)
resource "aws_s3_bucket_policy" "bucket_policy" {
  bucket = aws_s3_bucket.secure_bucket.id
  policy = data.aws_iam_policy_document.bucket_policy.json

  depends_on = [aws_s3_bucket_public_access_block.bucket_public_access]
}

data "aws_iam_policy_document" "bucket_policy" {
  statement {
    sid    = "DenyPublicReadAccess"
    effect = "Deny"
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject"
    ]
    resources = [
      "${aws_s3_bucket.secure_bucket.arn}/*"
    ]
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }

  statement {
    sid    = "DenyPublicListAccess"
    effect = "Deny"
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    actions = [
      "s3:ListBucket"
    ]
    resources = [
      aws_s3_bucket.secure_bucket.arn
    ]
  }
}

# Outputs
output "bucket_name" {
  value = aws_s3_bucket.secure_bucket.id
}

output "bucket_arn" {
  value = aws_s3_bucket.secure_bucket.arn
}

output "bucket_website_url" {
  value = aws_s3_bucket.secure_bucket.website_endpoint
}
```

### Prompt 2: GitHub Actions Workflow

```yaml
# .github/workflows/docker-build.yml
name: Docker Build and Push

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  test-and-build:
    runs-on: ubuntu-latest
    
    permissions:
      contents: read
      packages: write
      security-events: write
    
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      
      - name: Cache Docker layers
        uses: actions/cache@v3
        with:
          path: /tmp/.buildx-cache
          key: ${{ runner.os }}-buildx-${{ github.sha }}
          restore-keys: |
            ${{ runner.os }}-buildx-
      
      - name: Log in to Container Registry
        if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Extract metadata (tags, labels) for Docker
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=ref,event=branch
            type=ref,event=pr
            type=semver,pattern={{version}}
            type=sha,format=long
      
      - name: Build and test Docker image
        uses: docker/build-push-action@v5
        with:
          context: .
          push: false
          load: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=local,src=/tmp/.buildx-cache
          cache-to: type=local,dest=/tmp/.buildx-cache-new,mode=max
          target: test  # Assuming a test stage in Dockerfile
      
      - name: Run unit tests
        run: |
          docker run --rm ${{ steps.meta.outputs.tags }} pytest tests/ -v --cov=app --cov-report=xml
      
      - name: Upload test coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
          flags: unittests
          name: codecov-umbrella
          fail_ci_if_error: false
      
      - name: Run security scan (Trivy)
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: ${{ steps.meta.outputs.tags }}
          format: 'sarif'
          output: 'trivy-results.sarif'
          severity: 'CRITICAL,HIGH'
      
      - name: Upload Trivy results to GitHub Security tab
        uses: github/codeql-action/upload-sarif@v2
        if: always()
        with:
          sarif_file: 'trivy-results.sarif'
      
      - name: Push to registry (main branch only)
        if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=local,src=/tmp/.buildx-cache
          cache-to: type=local,dest=/tmp/.buildx-cache-new,mode=max
      
      - name: Move cache
        run: |
          rm -rf /tmp/.buildx-cache
          mv /tmp/.buildx-cache-new /tmp/.buildx-cache
      
      - name: Deploy to staging
        if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        run: |
          echo "Deploying ${{ steps.meta.outputs.tags }} to staging environment..."
          # Add deployment commands here (e.g., kubectl set image, helm upgrade)
      
      - name: Notify on failure
        if: failure()
        uses: actions/github-script@v6
        with:
          script: |
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: '❌ Build or tests failed for commit ${{ github.sha }}. Please check the logs.'
            })
```

**Example Dockerfile with test stage:**

```dockerfile
# Dockerfile
FROM python:3.11-slim as base

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Test stage
FROM base as test
RUN pip install pytest pytest-cov
CMD ["pytest", "tests/", "-v"]

# Production stage
FROM base as production
CMD ["python", "app.py"]
```
