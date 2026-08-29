# Safe source-review packaging

scripts/package_review.ps1 creates a review ZIP intended for source and
documentation review. It does not package runtime state or secrets.

The script:

1. resolves the requested source root and output path;
2. builds a temporary staging tree;
3. excludes secret environment filenames (.env and .env.*), key/certificate
   material, credentials, virtual environments, vendor cache, VCS metadata,
   runtime/cache directories, logs, SQLite/DB files, and prior review artifacts;
4. checks the staged manifest for any remaining secret environment filename
   before creating the ZIP;
5. writes the archive only after that manifest check, then removes staging.

It never needs to read the contents of an excluded secret file. A suspicious
secret filename is never copied into staging; if one somehow appears there,
packaging fails closed. The deterministic test
tests/test_review_packaging.py exercises .env.local, .venv, .git,
vendor_cache, runtime state, and database exclusions.

The default output is the separately git-ignored `artifacts/` directory. An explicit destination can also be supplied:

powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/package_review.ps1 -OutputPath $env:TEMP/meridian-alpha-source-review.zip

Do not attach or commit an archive containing secrets. The current project
review was verified from a synthetic fixture; no current secret file was
opened or included.
