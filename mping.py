from multiprocessing.pool import ThreadPool
from typing import List, Optional, Tuple
import argparse
import ipaddress
import pandas as pd
import sys

import dns.resolver
import dns.reversename
import ping3
ping3.EXCEPTIONS = True


def main():
    DEFAULT_THREADS = 2048
    DEFAULT_PING_COUNT = 4
    parser = argparse.ArgumentParser(
        prog="python " + sys.argv[0],
        description="Ping a subnet"
    )
    parser.add_argument(
        "subnet",
        action="store",
        help="The subnet to ping",
    )
    parser.add_argument(
        "--csv",
        action="store",
        dest="to_csv",
        help="Output to a csv. Includes raw output of the commands."
    )
    parser.add_argument(
        "-t",
        action="store",
        dest="n_threads",
        default=DEFAULT_THREADS,
        type=int,
        help=f"The number of threads to ping with. Default: {DEFAULT_THREADS}"
    )
    parser.add_argument(
        "-n",
        action="store",
        dest="n_pings",
        default=DEFAULT_PING_COUNT,
        type=int,
        help=f"The number of pings to do. Default: {DEFAULT_PING_COUNT}"
    )
    parser.add_argument(
        "--dns",
        action="store",
        dest="dns_server",
        help="The DNS to use for nslookup"
    )
    args = parser.parse_args()
    subnet = args.subnet
    to_csv = args.to_csv
    n_threads = args.n_threads
    n_pings = args.n_pings
    dns_server = args.dns_server

    if n_threads <= 0:
        parser.error("Threads must be greater than 0")

    if n_pings <= 0:
        parser.error("Pings must be greater than 0")

    try:
        subnet = ipaddress.IPv4Network(subnet, strict=False)
    except ipaddress.AddressValueError:
        parser.error("Not a valid address")
        return
    except ipaddress.NetmaskValueError:
        parser.error("Not a valid subnet")
        return

    if subnet.prefixlen < 16:
        parser.error("Too broad a subnet. Must be >= 16")
        return

    print(f"Pinging:   {subnet}")
    print()
    print(f"Mask:      {subnet.netmask}")
    print(f"Cidr:      {subnet.prefixlen}")
    print(f"Network:   {subnet.network_address}")
    print(f"Broadcast: {subnet.broadcast_address}")

    # Returns a list of ips inside the specified subnet
    ips = list(subnet.hosts())

    # Final chance to abort
    print()
    print("Pinging {} time{} for {} IP{} in range using {} thread{}:".format(
        n_pings,
        "s" if n_pings > 1 else "",
        len(ips),
        "s" if len(ips) > 1 else "",
        min(n_threads, len(ips)),
        "s" if n_threads > 1 else ""
    ))
    if len(ips) > 1:
        print("{} -> {}".format(ips[0], ips[-1]))

    if to_csv is not None:
        print(f"Once done will save to {to_csv}")

    print()
    print("Press enter to continue (ctrl+c to cancel)")
    try:
        input()
    except KeyboardInterrupt:
        return


    def ping(ip):
        print(f"Pinging {ip}")
        responses = []
        for _ in range(n_pings):
            try:
                response_time = ping3.ping(
                    str(ip),
                    unit="ms"
                )
                responses.append("{}ms".format(round(response_time)))
            except ping3.errors.PingError:
                responses.append("_")

        dns_responses = []
        try:
            dns_resolver = dns.resolver.Resolver()
            if dns_server is not None:
                dns_resolver.nameservers = [dns_server]
            reverse_name = dns.reversename.from_address(str(ip))
            answer = dns_resolver.resolve(reverse_name, "PTR")
            for rdata in answer:
                dns_responses.append(rdata.to_text())
        except Exception:
            pass

        return (ip, ", ".join(responses), ",".join(dns_responses))

    results: List[Tuple[str, int, Optional[str], str, Optional[str]]] = []
    try:
        with ThreadPool(min(n_threads, len(ips))) as tp:
            results = tp.map(ping, ips)
    except KeyboardInterrupt:
        print()
        print("Killing threads")
        return

    df = pd.DataFrame.from_records(results, columns=["ip", "responses", "nslookup"])

    print(df.to_markdown())

    if to_csv is not None:
        try:
            print(f"Writing {to_csv}")
            with open(to_csv, "w", encoding="utf-8") as f:
                f.write(df.to_csv(lineterminator="\n"))
        except PermissionError:
            print(f"Cannot write to {to_csv} at the moment. Using stdout.")
            print()
            print(df.to_markdown())


if __name__ == "__main__":
    main()
