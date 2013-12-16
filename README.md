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

Extending Trigger
-----------------

Trigger can be extended through drivers and extensions. Drivers implement core functionality and are broken into three drivers:

### Drivers ###

* LockDriver

  Handles locking of deployment for a repository.

* SyncDriver

  Handles the actual deployment. This driver will generally handle deployments via two separate fetch and checkout stages.

* ServiceDriver (slated for 0.3 release)

  Handles the service call methods (service start/stop/restart/reload/etc.)

Drivers are installed in drivers/<drivername>/<driver>.py and can be configured via git using deploy.sync-driver, deploy.lock-driver and deploy.sync-driver. For instance, trebuchet local drivers are handled like so:

Installed at: drivers/trebuchet/local.py (implements SyncDriver and LockDriver)

Configured using:

* deploy.sync-driver: trebuchet.local.SyncDriver
* deploy.lock-driver: trebuchet.local.LockDriver

### Extensions ###

Extensions are able to extend the command line to add extra actions. Extensions are installed in extensions/<extension>.py. Functions beginning with do\_ are turned into cli actions. Decorators can be used to extend argparse for this action.

Example extension:

    from trigger import config
    from trigger import utils
    from trigger.extension import Extension

    LOG = config.LOG


    @utils.arg('--big',
               dest='big',
               action='store_true',
               default=False,
               help='Make big dog sounds rather than small dog sounds.')
    def do_bark( args):
        if args.big:
            LOG.info('WOOF')
        else:
            LOG.info('woof')

Example usage:

```bash
$ cd <repo>

<repo>$ git trigger bark
INFO:woof

<repo>$ git trigger bark --big
INFO:WOOF

<repo>$ git help bark
usage: trigger bark [--big]

optional arguments:
  --big  Make big dog sounds rather than small dog sounds.
```
