# POSProctor Authentication Guide

POSProctor supports two authentication modes:
- **None** (no authentication) - Default
- **Microsoft Entra ID** (Azure AD SSO)

## Current Status

✅ **Partial Authentication is fully implemented**

**Completed:**
- ✅ Auth module created ([webapp/auth.py](../webapp/auth.py))
- ✅ Login template created
- ✅ Authentication routes added (`/login`, `/logout`, `/auth/entra`, `/auth/callback`)
- ✅ Dependencies added (Flask-Login, MSAL)
- ✅ `@protected_route` decorator for protected routes
- ✅ Public routes (Dashboard, Transactions) accessible without login
- ✅ Protected routes (Commanders, Passwords, Configuration) require authentication
- ✅ "Entra Login" button in navbar when not authenticated
- ✅ Conditional menu items based on authentication state
- ✅ Auth config available to all templates via context processor

**Deployment Status:**
- ✅ Webapp container rebuilt with authentication dependencies
- ✅ Currently running with `AUTH_TYPE=none` (no authentication)
- ✅ Ready to enable Entra authentication when needed

## How Partial Authentication Works

When authentication is **enabled** (`AUTH_TYPE=entra`), POSProctor implements a **partial authentication model**:

### Public Routes (No Login Required)
- 🌐 **Dashboard** (`/`) - View statistics and links to monitoring tools
- 🌐 **Grafana Links** - Access Grafana dashboards
- 🌐 **Transactions** (`/tlogs`) - View and analyze transaction logs

### Protected Routes (Login Required)
- 🔒 **Commanders** (`/commanders`) - Manage commander configuration
- 🔒 **Passwords** (`/passwords`) - Manage commander passwords
- 🔒 **Configuration** (`/config`) - Modify application settings

### User Experience
1. **Without Login**: Users see Dashboard and Transactions menu items, plus an "Entra Login" button in the navbar
2. **After Login**: Commanders, Passwords, and Configuration menu items appear and become accessible
3. **Protected Routes**: Direct access to protected routes redirects to login page with return URL

This design allows monitoring and analysis features to be accessible to all users, while restricting administrative functions to authenticated users.

## Configuration

Authentication is configured via environment variables in `docker-compose.yml`:

### No Authentication (Default)

```yaml
environment:
  - AUTH_TYPE=none
```

All routes are publicly accessible. No login required. All menu items visible.

### Microsoft Entra ID (Azure AD)

```yaml
environment:
  - AUTH_TYPE=entra
  - ENTRA_CLIENT_ID=your-client-id
  - ENTRA_CLIENT_SECRET=your-client-secret
  - ENTRA_TENANT_ID=your-tenant-id
  - ENTRA_REDIRECT_URI=https://your-domain.com/auth/callback
```

## Setting Up Entra ID

### 1. Register Application in Azure Portal

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to **Azure Active Directory** > **App registrations**
3. Click **New registration**
4. Configure:
   - **Name**: POSProctor
   - **Supported account types**: Single tenant
   - **Redirect URI**: Web - `https://your-domain.com/auth/callback`
5. Click **Register**

### 2. Get Credentials

From your app registration:

**Application (client) ID**:
- Copy this to `ENTRA_CLIENT_ID`

**Directory (tenant) ID**:
- Copy this to `ENTRA_TENANT_ID`

**Client Secret**:
1. Go to **Certificates & secrets**
2. Click **New client secret**
3. Add description and expiration
4. Copy the **Value** (not ID) to `ENTRA_CLIENT_SECRET`
5. ⚠️ **Important**: Copy immediately - it won't be shown again!

### 3. Configure API Permissions

1. Go to **API permissions**
2. Ensure these permissions are present:
   - Microsoft Graph > User.Read (Delegated)
3. Click **Grant admin consent** if required

### 4. Configure Authentication

1. Go to **Authentication**
2. Under **Redirect URIs**, ensure your callback URL is listed:
   - `https://your-domain.com/auth/callback`
   - `https://localhost/auth/callback` (for testing)
3. Under **Implicit grant and hybrid flows**:
   - Enable **ID tokens**
4. Click **Save**

### 5. Update Environment Variables

Update `docker-compose.yml` or create `.env` file:

```bash
AUTH_TYPE=entra
ENTRA_CLIENT_ID=12345678-1234-1234-1234-123456789012
ENTRA_CLIENT_SECRET=your~secret~value~here
ENTRA_TENANT_ID=98765432-4321-4321-4321-210987654321
ENTRA_REDIRECT_URI=https://your-domain.com/auth/callback
```

### 6. Restart Services

```bash
docker-compose down
docker-compose build webapp
docker-compose up -d
```

## Testing Authentication

### Test Entra ID Flow

1. Set `AUTH_TYPE=entra` with valid credentials
2. Navigate to `https://your-domain.com`
3. Should redirect to `/login`
4. Click **Sign in with Microsoft**
5. Authenticate with Microsoft account
6. Should redirect back to dashboard

### Verify User Session

When logged in:
- Username appears in top-right navbar
- Logout button visible
- All routes accessible

## Troubleshooting

### "Microsoft Entra ID is not configured"

**Cause**: Missing or invalid Entra environment variables

**Solution**:
- Verify `ENTRA_CLIENT_ID`, `ENTRA_TENANT_ID`, and `ENTRA_CLIENT_SECRET` are set
- Check for typos in environment variables
- Ensure no quotes around values in `.env`

### "Authentication failed" after Microsoft login

**Cause**: Redirect URI mismatch

**Solution**:
- Ensure `ENTRA_REDIRECT_URI` matches exactly what's configured in Azure Portal
- Include protocol (`https://`) and full path (`/auth/callback`)
- Check Azure Portal > App registrations > Authentication > Redirect URIs

### Redirect loop or 404 after login

**Cause**: Route not protected with decorator

**Solution**:
- Ensure all routes (except `/health`, `/login`, `/logout`, `/auth/*`) have `@login_required_conditional` decorator
- Check `app.py` for missing decorators

### "Invalid client secret"

**Cause**: Client secret expired or incorrect

**Solution**:
- Generate new client secret in Azure Portal
- Update `ENTRA_CLIENT_SECRET` environment variable
- Rebuild and restart containers

## Security Considerations

### Production Deployment

1. **Use HTTPS**: Entra ID requires HTTPS for production
2. **Secure Secrets**: Use Docker secrets or external secret management
3. **Network Security**: Run behind nginx with SSL/TLS
4. **Regular Rotation**: Rotate client secrets periodically
5. **Monitor Access**: Review Azure AD sign-in logs

### Recommended Settings

```yaml
# docker-compose.yml
environment:
  - AUTH_TYPE=entra
  - FLASK_SECRET_KEY=${FLASK_SECRET_KEY}  # Generate with: openssl rand -hex 32
  - ENTRA_CLIENT_ID=${ENTRA_CLIENT_ID}
  - ENTRA_CLIENT_SECRET=${ENTRA_CLIENT_SECRET}
  - ENTRA_TENANT_ID=${ENTRA_TENANT_ID}
  - ENTRA_REDIRECT_URI=https://posproctor.yourdomain.com/auth/callback
```

Store actual values in `.env` file (gitignored):

```bash
# .env
FLASK_SECRET_KEY=your-random-secret-key-here
ENTRA_CLIENT_ID=12345678-1234-1234-1234-123456789012
ENTRA_CLIENT_SECRET=your~secret~value~here
ENTRA_TENANT_ID=98765432-4321-4321-4321-210987654321
ENTRA_REDIRECT_URI=https://posproctor.yourdomain.com/auth/callback
```

## Disabling Authentication

To disable authentication and make all routes public:

```yaml
environment:
  - AUTH_TYPE=none
```

Or remove/comment out the `AUTH_TYPE` variable entirely (defaults to `none`).

## API Authentication

The authentication system applies to the web UI only. Internal service-to-service API calls use:

- TLOG API: `TLOG_API_KEY`
- Bitwarden: Service-to-service auth
- Monitoring: Internal network only

## Future Enhancements

Potential authentication features for future versions:

- Multi-factor authentication (MFA)
- API tokens for programmatic access
- Role-based access control (RBAC)
- SAML SSO support
- LDAP integration
- Session timeout configuration
- Audit logging

## References

- [Microsoft Authentication Library (MSAL) for Python](https://github.com/AzureAD/microsoft-authentication-library-for-python)
- [Flask-Login Documentation](https://flask-login.readthedocs.io/)
- [Microsoft identity platform documentation](https://docs.microsoft.com/en-us/azure/active-directory/develop/)
