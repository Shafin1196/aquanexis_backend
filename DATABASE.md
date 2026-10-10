# Database configuration

The project uses SQLite for local development by default. To connect to the
Aiven MySQL database, install the project requirements and set these environment
variables in the server environment (for example, the Render service settings):

```text
DB_ENGINE=mysql
DB_NAME=defaultdb
DB_USER=avadmin
DB_PASSWORD=<rotated database password>
DB_HOST=<Aiven host>
DB_PORT=<Aiven port>
```

The Aiven CA certificate is included at `certs/aiven-ca.pem` and is used by
default. If you provide the certificate separately (for example, as a hosting
provider secret file), set `DB_SSL_CA` to its absolute path. The certificate
allows TLS to verify the database server. Keep the password in the hosting
provider's secret/environment settings; do not put it in source code or commit
it.

After setting the environment variables and installing requirements, deploy
the schema with:

```powershell
python manage.py migrate
```

This creates or updates tables in MySQL; it does not copy existing rows from
the local SQLite database. Back up and migrate any data that must be retained
before switching production traffic.

The database password shown in a screenshot or shared message should be
considered exposed. Rotate it in Aiven before configuring the application.
