import os
import time

import git
from logs import log

ROOT_DIR = os.path.dirname(os.path.realpath(__file__))


class AutoUpdater:
    def __init__(self, is_on_gcp=False):
        self.is_on_gcp = is_on_gcp
        self.last_update_check_time = None
        if not self.is_on_gcp:
            log.info('Not pulling latest on non-gcp machines, assuming you are '
                     'in dev')

    def updated(self) -> bool:
        """
        :return: Whether or not we updated our local repo
        """
        now = time.time()
        if not self.is_on_gcp:
            ret = False
        elif self.last_update_check_time is not None:
            log.debug('Checking for source changes')
            if now - self.last_update_check_time > 3:
                ret = self.pull_latest(now)
                self.last_update_check_time = time.time()
            else:
                ret = False
        else:
            ret = self.pull_latest(now)
            self.last_update_check_time = time.time()
        return ret

    def pull_latest(self, now):
        log.debug('Pulling latest from github..')
        self.last_update_check_time = now
        if pull_latest():
            log.success('Pulled new changes')
            ret = True
        else:
            ret = False
        return ret


def pull_latest(check_first=False, remote_branch='production'):
    ret = False
    repo = git.Repo(ROOT_DIR)
    if check_first:
        origin = [r for r in repo.remotes if r.name == 'origin'][0]

        # Fetch all origin changes
        origin.update()

        head = repo.head.commit.hexsha
        prod = [b for b in origin.refs
                if b.name == f'origin/{remote_branch}'][0]

        prod_head = prod.commit.hexsha
        should_pull = head != prod_head
    else:
        should_pull = True

    if should_pull:
        pull_result = repo.git.pull('origin', remote_branch)
        if pull_result != 'Already up to date.':
            ret = True
            log.info(pull_result)

    return ret


if __name__ == '__main__':
    pull_latest()
