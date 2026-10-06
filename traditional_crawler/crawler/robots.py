from urllib.robotparser import RobotFileParser
from urllib.parse import urljoin


def create_robots_parser(start_url: str) -> RobotFileParser:
    robots_url = urljoin(start_url, "/robots.txt")

    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.read()

    return parser