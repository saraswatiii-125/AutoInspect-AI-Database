# Backend Authentication & Authorization Architecture

**AutoInspect AI — Branch 1**  
**Document Date:** November 8, 2026 (Completed through Step 40)

---

## 1. Cryptographic Standards

### Password Hashing
- **Algorithm:** Argon2id (`Type 2`) via `argon2-cffi`.
- **Parameters:**
  - Memory Cost: 65,536 KiB (64 MiB RAM)
  - Time Cost: 3 iterations
  - Parallelism: 4 threads/lanes
  - Hash Length: 32 bytes
  - Salt: Cryptographically secure random 16-byte salt per password
- **Anti-Enumeration Defense:**
  - If a login attempt specifies an unrecognized email, the backend verifies against a valid, precomputed Argon2id dummy hash generated at application startup (`_DUMMY_ARGON2_HASH`).
  - This guarantees identical execution timing between existing and non-existing accounts, neutralizing user-enumeration side-channel timing attacks.
- **CPU Exhaustion Mitigation:**
  - Login password field enforces `max_length=128` characters to prevent denial of service through oversized inputs submitted to Argon2id.

### Token Issuance & Verification
- **Algorithm:** HS256 (HMAC with SHA-256) via `pyjwt`.
- **Default Lifetime:** 60 minutes (configurable via `ACCESS_TOKEN_EXPIRE_MINUTES`).
- **Secret Key:** `JWT_SECRET_KEY` loaded from environment variables (enforces minimum length of 32 characters for 256-bit cryptographic strength).
- **Token Claims Payload:**
  - `sub`: Authenticated user ID (integer converted to string).
  - `type`: Strictly `"access"`.
  - `iat`: Timestamp of issue (UTC integer).
  - `exp`: Timestamp of expiration (UTC integer).
  - `role`: User role retrieved from the database.

---

## 2. Authentication Dependency (`get_current_user`)

Located in `backend/app/core/dependencies.py`:

```python
def get_current_user(
    auth_credentials: Optional[HTTPAuthorizationCredentials] = Depends(_http_bearer),
    db: Session = Depends(get_db),
) -> UserModel:
```

1. **Header Extraction:** Extracts credentials strictly via `HTTPBearer(auto_error=False)` from the `Authorization: Bearer <token>` header.
2. **Missing Token Handling:** Rejects unauthenticated requests with HTTP 401 Unauthorized and standard RFC 6750 header: `WWW-Authenticate: Bearer`.
3. **Signature & Expiration Validation:** Validates HS256 signature and `exp` timestamp. Expired or altered tokens trigger HTTP 401.
4. **Token Type Enforcement:** Ensures `payload.get("type") == "access"`.
5. **Database-Backed Identity:** Parses `payload.get("sub")` as an integer ID and loads the user from `public.users` via `db.query(UserModel).filter(UserModel.id == user_id).first()`.
6. **No Role Spoofing:** User role is read directly from `UserModel.role` in the database. Client-supplied token claims for role are discarded during authorization checks.

---

## 3. Role-Based Access Control (RBAC) & Ownership Scoping

### Role Separation
- **`admin`**: Global visibility. Can view, create, edit, and delete all customer vehicles and inspections, as well as legacy unassigned records.
- **`customer`**: Strictly isolated tenant. Can only access vehicles where `VehicleModel.user_id == current_user.id`, and inspections where `VehicleModel.user_id == current_user.id`.
- **Any Other Role**: Any unrecognized role string (e.g. `"guest"`, `"mechanic"`) receives **HTTP 403 Forbidden**.

### Endpoint Enforcement Summary

| Resource | Operation | Admin Access | Customer Access | Error Handling |
|---|---|---|---|---|
| `/api/vehicles` | List (GET) | All vehicles | Only `user_id == user.id` | Returns `[]` if none owned |
| `/api/vehicles/{id}` | Read (GET) | Any vehicle | Only if owned | **404 Not Found** if unowned |
| `/api/vehicles` | Create (POST) | Any vehicle; stamps admin `user_id` | Stamps `user_id = user.id` | 422 if `user_id` in body |
| `/api/vehicles/{id}` | Update (PUT) | Any vehicle; allowlist fields | Only if owned; allowlist fields | **404 Not Found** if unowned |
| `/api/vehicles/{id}` | Delete (DELETE) | Any vehicle | Only if owned | **404 Not Found** if unowned |
| `/api/inspections` | List (GET) | All inspections | Only if parent vehicle owned | Returns `[]` if none owned |
| `/api/inspections/{id}` | Read (GET) | Any inspection | Only if parent vehicle owned | **404 Not Found** if unowned |
| `/api/inspections` | Create (POST) | Any existing vehicle | Only if parent vehicle owned | **404 Not Found** if unowned vehicle |

---

## 4. Security Hardening Controls (Batch 4, Steps 37–38)

### 4.1 Rate Limiting (`app/core/rate_limiter.py`)
- In-memory sliding-window rate limiter protects sensitive endpoints:
  - `POST /api/auth/login`: Limited to 10 requests per minute per client IP.
  - `POST /api/auth/register`: Limited to 5 requests per minute per client IP.
- Excess requests return **HTTP 429 Too Many Requests** with `Retry-After: <seconds>`.

### 4.2 Security Headers (`app/main.py`)
High-performance pure ASGI middleware injects security headers onto every response:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`
- `Content-Security-Policy: default-src 'self'; frame-ancestors 'none';`

### 4.3 Host Header Validation (`TrustedHostMiddleware`)
- Enforces an explicit host whitelist (`localhost`, `127.0.0.1`, `testserver`).
- Forged host headers return **HTTP 400 Bad Request**.

### 4.4 Request Body Size Limit (`RequestSizeLimitMiddleware`)
- Rejects requests exceeding 15 MB with **HTTP 413 Payload Too Large** prior to payload buffering.

### 4.5 Global Unhandled Exception Masking
- All unhandled exceptions return a generic HTTP 500 error: `"An unexpected server error occurred. Please try again later."`
- Guarantees zero leakage of stack traces, database credentials, or internal paths.
- Preserves standard HTTP exceptions (401, 403, 404, 422, 429).
