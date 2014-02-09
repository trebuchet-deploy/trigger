#!/usr/bin/python
import subprocess


def main():
    try:
        f = open('.git', 'r')
        subgitdir = f.read()
        f.close()
    except (IOError, OSError):
        raise SystemExit(1)
    subgitdir = subgitdir.replace('gitdir: ', '').strip()
    cmd = 'git update-server-info'
    p = subprocess.Popen(cmd, shell=True, cwd=subgitdir)
    p.communicate()


if __name__ == "__main__":
    main()
