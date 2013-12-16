trigger
=======

Trebuchet git interface

Installation
------------

### Using pip ###

```bash
sudo pip install TrebuchetTrigger
```

Configuration
-------------

The configuration of trigger depends on the drivers in use. The default drivers are:

* trebuchet.local.SyncDriver
* trebuchet.local.FileDriver
* trebuchet.local.ServiceDriver

Configuration is done through git. Some configuration items should be added in the user's global configuration while other configuration should be added in the repository's configuration or system configuration. Trigger will refuse to run if these configuration items are not set.

User's global configuration:

* user.name
* user.email

Repo configuration:

* deploy.repo-name
* deploy.sync-driver (has default; can also be set system-wide)
* deploy.file-driver (has default; can also be set system-wide)
* deploy.service-driver (has default; can also be set system-wide)

System configuration:

* deploy.sync-driver (has default; can also be set per-repo)
* deploy.file-driver (has default; can also be set per-repo)
* deploy.service-driver (has default; can also be set per-repo)

### Trebuchet local driver configuration ###

At this time the trebuchet local drivers require no extra configuration.

Usage
-----

The usage of trigger depends on the drivers in use.

### Trebuchet local driver ###

The local drivers assume that you are using a centralized deployment server that hosts the repositories used by your minions. Teams of developers manage the repositories and deployments are done directly from the server. Locking is done locally, per-repository. The sync driver will make calls directly to salt via sudo.

The basic usage is:

```bash
$ cd <repo>

<repo>$ git trigger start
INFO:Deployment started.

<repo>$ <make local git changes>

<repo>$ git trigger sync
INFO:Synchronization started
INFO:Fetch stage started
INFO:Repo: test/testrepo; checking tag: test/testrepo-20131216-030825

0 minions pending (1 reporting)

Continue? ([d]etailed/[C]oncise report,[y]es,[n]o,[r]etry): y

INFO:Checkout stage started
INFO:Repo: test/testrepo; checking tag: test/testrepo-20131216-030825

0 minions pending (1 reporting)

Continue? ([d]etailed/[C]oncise report,[y]es,[n]o,[r]etry): y

INFO:Deployment finished.
```

To abort a deployment:

```bash
<repo>$ git trigger abort
INFO:Deployment aborted.
```

To manage services:

```bash
<repo>$ git trigger service start
INFO:Service started.

<repo>$ git trigger service stop
INFO:Service stopped.

<repo>$ git trigger service restart
INFO:Service restarted.

<repo>$ git trigger service reload
INFO:Service reloaded.
```
