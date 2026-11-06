# UI design

The console is server-rendered with Jinja2 and hand-written CSS. It has no frontend framework, build chain or third-party CDN.

## Design principles

- Readable, dense operational UI with clear state labels and honest empty/error states.
- Core flows must work without JavaScript; progressive enhancement only for dialogs, async feedback and copying tokens.
- Light and dark themes share design tokens; layouts must work at 1440, 1024/900 and 390 widths.
- Destructive actions require confirmation; secrets are never echoed back.

## Pages

| Page | Route | Purpose |
|---|---|---|
| Overview | `/` | Personal overview for every role (queryable targets, own tokens, own recent calls); admins also see a link to the admin overview |
| Admin overview | `/admin/overview` | Global target health, items needing attention and recent operations (admins only) |
| Targets | `/targets` | Target directory, environment tabs, connection test, edit, enable/disable, delete; read-only view for analysts |
| New/edit target | `/targets/new`, `/targets/{id}/edit` | Type-specific form; new targets must pass a connection test; connection-field changes trigger re-probe |
| Environments | `/environments` | Environment title/key/enable-to-disable management (admins) |
| Audit | `/audit` | Filter by time/action/environment/outcome/object; detail dialog with failure reason; analysts see their own tool calls |
| Settings | `/settings` | Runtime policy grouped by section; read-only security/startup/history views |
| Users | `/users` | Admin-created accounts, roles, enable/disable, password reset |
| My account | `/me` | Profile, MCP tokens, password change |

## Interaction rules

- Forms submit to the server; validation and authorization remain server-side.
- Non-JavaScript fallbacks use dedicated pages or explicit copy hints; no fake interactive elements.
- Long lists paginate; tables collapse to cards on narrow screens.
- Error messages identify the field or action and never include secrets.

## Visual system

- Tokens centralize background/surface/border/text/accent/semantic colors, shadows, radii, spacing and typography.
- Sidebar navigation groups: Overview, Investigate (Targets, Environments), Records (Audit), System (Settings, Users, My account).
- The brand block uses a rounded 36px logo container with a two-line title and navigation aligned to the same content edge.
