import argparse
import os
import logging
import colorama
from colorama import Fore, Style
from . import client  # Importing client from a module named "client"
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import requests
from collections import defaultdict
import time

yellow_color_code = "\033[93m"
reset_color_code = "\033[0m"

colorama.init(autoreset=True)  # Initialize colorama for colored terminal output

log_format = '%(message)s'
logging.basicConfig(format=log_format, level=logging.INFO)
logging.getLogger('').handlers[0].setFormatter(logging.Formatter(log_format))

HARDCODED_EXTENSIONS = [
    ".jpg", ".jpeg", ".png", ".gif", ".pdf", ".svg", ".json",
    ".css", ".js", ".webp", ".woff", ".woff2", ".eot", ".ttf", ".otf", ".mp4", ".txt"
]

def has_extension(url, extensions):
    """
    Check if the URL has a file extension matching any of the provided extensions.

    Args:
        url (str): The URL to check.
        extensions (list): List of file extensions to match against.

    Returns:
        bool: True if the URL has a matching extension, False otherwise.
    """
    parsed_url = urlparse(url)
    path = parsed_url.path
    extension = os.path.splitext(path)[1].lower()

    return extension in extensions

def clean_url(url):
    """
    Clean the URL by removing redundant port information for HTTP and HTTPS URLs.

    Args:
        url (str): The URL to clean.

    Returns:
        str: Cleaned URL.
    """
    parsed_url = urlparse(url)
    
    if (parsed_url.port == 80 and parsed_url.scheme == "http") or (parsed_url.port == 443 and parsed_url.scheme == "https"):
        parsed_url = parsed_url._replace(netloc=parsed_url.netloc.rsplit(":", 1)[0])

    return parsed_url.geturl()

def clean_urls(urls, extensions, placeholder=None):
    """
    Clean a list of URLs by removing unnecessary parameters and query strings.

    Args:
        urls (list): List of URLs to clean.
        extensions (list): List of file extensions to check against.
        placeholder (str): Placeholder for parameter values. If None, keep the original values.

    Returns:
        list: List of cleaned URLs.
    """
    cleaned_urls = set()
    for url in urls:
        cleaned_url = clean_url(url)
        if not has_extension(cleaned_url, extensions):
            parsed_url = urlparse(cleaned_url)
            query_params = parse_qs(parsed_url.query)
            if placeholder:
                cleaned_params = {key: placeholder for key in query_params}
            else:
                cleaned_params = query_params
            cleaned_query = urlencode(cleaned_params, doseq=True)
            cleaned_url = parsed_url._replace(query=cleaned_query).geturl()
            cleaned_urls.add(cleaned_url)
    return list(cleaned_urls)

def merge_parameters(urls):
    """
    Merge parameters for the same endpoint into a single URL.

    Args:
        urls (list): List of URLs to process.

    Returns:
        list: List of merged URLs.
    """
    endpoint_params = defaultdict(dict)
    for url in urls:
        parsed_url = urlparse(url)
        params = parse_qs(parsed_url.query)
        endpoint = urlunparse(parsed_url._replace(query=""))

        for key, value in params.items():
            if key in endpoint_params[endpoint]:
                endpoint_params[endpoint][key].update(value)
            else:
                endpoint_params[endpoint][key] = set(value)

    merged_urls = []
    for endpoint, params in endpoint_params.items():
        merged_query = urlencode({key: list(values)[0] for key, values in params.items()}, doseq=True)
        merged_urls.append(urlunparse(urlparse(endpoint)._replace(query=merged_query)))

    return merged_urls

import time

def fetch_url_content(url, proxy, max_retries=5):
    """
    Fetch the content of the given URL with retry mechanism.

    Args:
        url (str): The URL to fetch.
        proxy (str): The proxy address to use for the request.
        max_retries (int): Maximum number of retries in case of failure.

    Returns:
        response: The HTTP response object or None if all retries fail.
    """
    retries = 0
    wait_time = 10  # Initial wait time in seconds

    while retries < max_retries:
        try:
            if proxy:
                response = requests.get(url, proxies={'http': proxy, 'https': proxy})
            else:
                response = requests.get(url)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            retries += 1
            logging.error(f"Error fetching URL {url}: {e}. Retrying in {wait_time} seconds...")
            time.sleep(wait_time)
            wait_time += 5  # Increase wait time for each retry
    
    logging.error(f"Failed to fetch URL {url} after {max_retries} retries.")
    return None

def fetch_and_clean_urls(domain, extensions, stream_output, proxy, placeholder=None, output_file=None):
    """
    Fetch and clean URLs related to a specific domain from the Wayback Machine.

    Args:
        domain (str): The domain name to fetch URLs for.
        extensions (list): List of file extensions to check against.
        stream_output (bool): True to stream URLs to the terminal.
        proxy (str): Proxy address for web requests.
        placeholder (str): Placeholder for parameter values. If None, keep the original values.
        output_file (str): Output file to save the cleaned URLs.

    Returns:
        None
    """
    logging.info(f"{Fore.YELLOW}[INFO]{Style.RESET_ALL} Fetching URLs for {Fore.CYAN + domain + Style.RESET_ALL}")
    wayback_uri = f"https://web.archive.org/cdx/search/cdx?url={domain}/*&output=txt&collapse=urlkey&fl=original&page=/"
    response = fetch_url_content(wayback_uri, proxy)
    if response is None:
        logging.error(f"{Fore.RED}[ERROR]{Style.RESET_ALL} Failed to fetch URLs for {domain}")
        return
    
    urls = response.text.split()
    logging.info(f"{Fore.YELLOW}[INFO]{Style.RESET_ALL} Found {Fore.GREEN + str(len(urls)) + Style.RESET_ALL} URLs for {Fore.CYAN + domain + Style.RESET_ALL}")
    
    cleaned_urls = clean_urls(urls, extensions, placeholder)
    logging.info(f"{Fore.YELLOW}[INFO]{Style.RESET_ALL} Cleaning URLs for {Fore.CYAN + domain + Style.RESET_ALL}")
    logging.info(f"{Fore.YELLOW}[INFO]{Style.RESET_ALL} Found {Fore.GREEN + str(len(cleaned_urls)) + Style.RESET_ALL} URLs after cleaning")
    
    merged_urls = merge_parameters(cleaned_urls)
    logging.info(f"{Fore.YELLOW}[INFO]{Style.RESET_ALL} Merging parameters for {Fore.CYAN + domain + Style.RESET_ALL}")
    logging.info(f"{Fore.YELLOW}[INFO]{Style.RESET_ALL} Found {Fore.GREEN + str(len(merged_urls)) + Style.RESET_ALL} URLs after merging")

    if output_file:
        mode = 'a' if os.path.exists(output_file) else 'w'
        with open(output_file, mode) as f:
            for url in merged_urls:
                f.write(url + "\n")
                if stream_output:
                    print(url)
        logging.info(f"{Fore.YELLOW}[INFO]{Style.RESET_ALL} Saved cleaned URLs to {Fore.CYAN + output_file + Style.RESET_ALL}")
    else:
        for url in merged_urls:
            if stream_output:
                print(url)
    
def main():
    """
    Main function to handle command-line arguments and start URL mining process.
    """
    log_text = """
                                      _    __       
   ___  ___ ________ ___ _  ___ ___  (_)__/ /__ ____
  / _ \/ _ `/ __/ _ `/  ' \(_-</ _ \/ / _  / -_) __/
/ .__/\_,_/_/  \_,_/_/_/_/___/ .__/_/\_,_/\__/_/   
/_/                          /_/                    

                              with <3 by @0xasm0d3us           
    """
    colored_log_text = f"{yellow_color_code}{log_text}{reset_color_code}"
    print(colored_log_text)
    
    parser = argparse.ArgumentParser(description="Mining URLs from dark corners of Web Archives")
    parser.add_argument("-d", "--domain", help="Domain name to fetch related URLs for.")
    parser.add_argument("-l", "--list", help="File containing a list of domain names.")
    parser.add_argument("-s", "--stream", action="store_true", help="Stream URLs on the terminal.")
    parser.add_argument("--proxy", help="Set the proxy address for web requests.", default=None)
    parser.add_argument("-p", "--placeholder", help="Placeholder for parameter values. If not provided, original values are kept.", default=None)
    parser.add_argument("-e", "--extensions", nargs='+', default=HARDCODED_EXTENSIONS, help="List of file extensions to exclude.")
    parser.add_argument("-o", "--output", help="Output file to save the cleaned URLs.")

    args = parser.parse_args()

    if not args.domain and not args.list:
        parser.error("Please provide either the -d option or the -l option.")

    if args.domain and args.list:
        parser.error("Please provide either the -d option or the -l option, not both.")

    domains = []
    if args.list:
        try:
            with open(args.list, "r") as f:
                domains = [line.strip().lower().replace('https://', '').replace('http://', '') for line in f.readlines()]
                domains = [domain for domain in domains if domain]  # Remove empty lines
                domains = list(set(domains))  # Remove duplicates
        except Exception as e:
            logging.error(f"Error reading domain list file: {e}")
            return
    else:
        domains.append(args.domain)

    extensions = args.extensions

    for domain in domains:
        output_file = args.output if args.output else f"{domain}.txt"
        fetch_and_clean_urls(domain, extensions, args.stream, args.proxy, args.placeholder, output_file)

if __name__ == "__main__":
    main()
