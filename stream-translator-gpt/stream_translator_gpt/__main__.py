from .common import configure_utf8_stdio

configure_utf8_stdio()

from .main import cli


if __name__ == '__main__':
    cli()
