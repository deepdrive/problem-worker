import os

import git
list(repo.references)
ROOT_DIR = os.path.dirname(os.path.realpath(__file__))


def main():
    repo = git.Repo(ROOT_DIR)
    origin = [r for r in repo.remotes if r.name == 'origin'][0]

    # Fetch all origin changes
    origin.update()

    head = repo.head.commit.hexsha
    prod = [b for b in origin.refs if b.name == 'origin/production'][0]

    prod_head = prod.commit.hexsha

    if head != prod_head:
        repo.git.pull()




if __name__ == '__main__':
    main()
