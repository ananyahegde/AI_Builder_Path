## Overview
This document compares four AI models - **GPT-4o**, **Claude Sonnet**, **Gemini Flash**, and **Deepseek** - across code generation, SQL generation, and infrastructure automation tasks relevant to AppDev, Data, and DevOps use cases.

## Models Used
| Model | Type | Access |
| --- | --- | --- |
| Claude Sonnet | Hosted | claude.ai |
| GPT-4o | Hosted | chatgpt.com |
| Gemini Flash | Hosted | share.gemini.google.com |
| Deepseek r1:7b | Hosted | chat.deepseek.com |

## Prompts Given

### AppDev — Code Generation
**Prompt 1:** Write a Python function that takes a list of user dictionaries (each with "name", "email", "signup_date") and returns only users who signed up in the last 30 days, sorted by signup_date descending. Handle missing/malformed dates gracefully.

**Prompt 2:** Refactor a given `process_queue` function to be thread-safe and add proper error handling with logging. Explain what race conditions existed in the original version.

### Data — SQL Generation
**Prompt 1:** Given tables `orders(order_id, customer_id, order_date, amount)` and `customers(customer_id, name, region)`, write a SQL query to find the top 3 customers by total order amount in each region, using a window function.

**Prompt 2:** Write a SQL query to detect customers who placed orders in Q1 but had zero orders in Q2 of the same year (churn detection). Explain how to optimize the query if the orders table has 50M+ rows.

### DevOps — Infrastructure Automation
**Prompt 1:** Write a Terraform config to provision an AWS S3 bucket with versioning enabled, server-side encryption, and a bucket policy that blocks all public access.

**Prompt 2:** Write a GitHub Actions workflow YAML that builds a Docker image, runs unit tests, and only pushes to a container registry if tests pass and the branch is "main". Include caching for dependencies to speed up builds.

## Comparison Table

| Model | Code Quality | SQL Generation | Infra Automation | Ease of Use | Speed/Latency | Comments |
| --- | --- | --- | --- | --- | --- | --- |
| **Claude Sonnet** | Excellent | Excellent | Excellent | Excellent | Good | Only one with a proper lock-based thread-safe queue and 4 clearly explained race conditions. SQL correctly flags RANK() vs ROW_NUMBER() tie behavior. Terraform + GitHub Actions YAML both clean with no syntax errors. |
| **GPT-4o** | Good | Good | Basic | Excellent | Excellent | Gave two redundant queue solutions instead of committing to one. GitHub Actions workflow has a YAML indentation error under the Python setup step. SQL logic correct but leans on EXTRACT(QUARTER) before addressing it in the optimization section. |
| **Gemini Flash** | Good | Excellent | Basic | Good | Excellent | DENSE_RANK choice well-justified. GitHub Actions workflow contains a corrupted line breaking the YAML, and the test step falls back between npm/pytest fragilely. |
| **Deepseek** | Basic | Basic | Not Supported | Basic | Good | Added unrequested scope (security scans, deploy stage, notify-on-failure). Churn SQL mixes NOT EXISTS logic with redundant extra joins. Terraform variable default illegally references a resource — will not compile. |
