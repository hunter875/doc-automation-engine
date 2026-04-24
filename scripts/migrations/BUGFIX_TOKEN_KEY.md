# Bug Fix: Token Not Persisted After Login (localStorage key mismatch)

## Problem
After login, `localStorage.getItem('access_token')` returns `null`, causing subsequent requests to fail with 401 Unauthorized.

**Symptoms:**
- User logs in successfully
- API call to `/api/v1/tenants/list` returns 401
- Checking browser console: `localStorage.getItem('access_token')` is `null`
- The token is actually stored under key `"token"` instead of `"access_token"`

## Root Cause
Inconsistent localStorage key naming:
- Backend returns `access_token` in login response
- Frontend `auth.ts` used to store with key `"token"` (hard-coded)
- Code checking for `'access_token'` (expected key) finds nothing → returns `null`
- Result: Requests after login don't include Authorization header → 401

## Fix Applied

### 1. Updated `frontend/lib/auth.ts`

**Changed storage key constant:**
```typescript
const STORAGE_KEYS = {
  TOKEN: "access_token",  // Was: "token"
  EMAIL: "email",
  TENANT_ID: "tenantId",
  TENANT_LIST: "tenantList",
} as const;
```

**Added fallback in `getToken()` for backward compatibility:**
```typescript
export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  // Try new key first, then fallback to old key
  return localStorage.getItem(STORAGE_KEYS.TOKEN) || localStorage.getItem("token");
}
```

**Enhanced `clearAuth()` to clean up old key:**
```typescript
export function clearAuth(): void {
  if (typeof window === "undefined") return;
  Object.values(STORAGE_KEYS).forEach((key) => {
    localStorage.removeItem(key);
  });
  // Also remove legacy token key
  localStorage.removeItem("token");
}
```

## Impact

- **New login**: Token saved with key `"access_token"` ✅
- **Existing users** (already logged in before this fix): `getToken()` still reads their old `"token"` key → works ✅
- **After logout**: Both keys cleared → clean state ✅
- **Next login**: Uses new key `"access_token"` ✅

## Testing Checklist

1. **Fresh login:**
   - Clear localStorage
   - Login with credentials
   - Check `localStorage.getItem('access_token')` → should have value
   - Check `/api/v1/tenants/list` request → should have `Authorization: Bearer <token>` header → 200 OK

2. **Backward compatibility (if any user still has old token):**
   - Manually set `localStorage.setItem('token', 'old-token-value')`
   - Refresh page
   - Verify `getToken()` returns the old token
   - Verify authenticated requests work

3. **Logout:**
   - Click logout
   - Check both `localStorage.getItem('token')` and `localStorage.getItem('access_token')` → both `null`

## Files Changed

- `frontend/lib/auth.ts`

---

**Deploy this fix immediately to resolve 401 errors after login.**
