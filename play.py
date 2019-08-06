import site
import docker
print(site.USER_BASE)


def main():
    cli = docker.from_env()
    cli.images.push('gcr.io/silken-impulse-217423/problem-worker-test')

if __name__ == '__main__':
    main()
