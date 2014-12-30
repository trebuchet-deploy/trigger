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
    p = subprocess.Popen(['git','update-server-info'], cwd=subgitdir)
    p.communicate()


if __name__ == "__main__":
    main()
