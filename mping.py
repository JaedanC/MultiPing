from multiprocessing.pool import ThreadPool
import ipaddress
import os
import pandas as pd
import re
import sys


class PingResult:
    def __init__(self, ping_result: str):
        ip_regex = re.compile(r"Pinging (?:(.*?) )with 32 bytes of data")
        stats_regex = re.compile(r"    Packets: Sent = (\d+), Received = (\d+), Lost = (\d+) \((\d+)% loss\),")
        time_regex = re.compile(r"    Minimum = (\d+)ms, Maximum = (\d+)ms, Average = (\d+)ms")
        self.ping_result = ping_result
        self.ip = None
        self.sent = None
        self.received = None
        self.lost = None
        self.lost_percent = None
        self.trip_time = None

        for line in ping_result.split("\n"):
            line_match = ip_regex.match(line)
            if line_match is not None:
                self.ip = line_match.group(1)
            
            line_match = stats_regex.match(line)
            if line_match is not None:
                self.sent = line_match.group(1)
                self.received = line_match.group(2)
                self.lost = line_match.group(3)
                self.lost_percent = line_match.group(4)
            
            line_match = time_regex.match(line)
            if line_match is not None:
                self.trip_time = "min: {}, max: {}, avg: {}".format(
                    line_match.group(1),
                    line_match.group(2),
                    line_match.group(3),
                )


class NSLookupResult:
    def __init__(self, nslookup_result: str):
        name_regex = re.compile(r"Name:\s+(.*)")
        self.nslookup_result = nslookup_result
        self.nslookup = None
        for line in nslookup_result.split("\n"):
            line_match = name_regex.match(line)
            if line_match is not None:
                self.nslookup = line_match.group(1)
                break


def subnet_calculator(ip_subnet):
    (addr, cidr) = ip_subnet.split('/')

    addr = [int(x) for x in addr.split(".")]
    cidr = int(cidr)
    mask = [( ((1<<32)-1) << (32-cidr) >> i ) & 255 for i in reversed(range(0, 32, 8))]
    netw = [addr[i] & mask[i] for i in range(4)]
    bcas = [(addr[i] & mask[i]) | (255^mask[i]) for i in range(4)]

    netw_str = '.'.join(map(str, netw))
    print("Address: {0}".format('.'.join(map(str, addr))))
    print("Mask: {0}".format('.'.join(map(str, mask))))
    print("Cidr: {0}".format(cidr))
    print("Network: {0}".format('.'.join(map(str, netw))))
    print("Broadcast: {0}".format('.'.join(map(str, bcas))))
    return list(ipaddress.ip_network("{}/{}".format(netw_str, cidr)).hosts())


def main():
    if len(sys.argv) < 2:
        print("multiping <ip/subnet> [options]")
        print("    --csv=<filename>       Output to a csv. Includes raw output of the commands.")
        print("    --threads=<numbers>    Change the number of threads used by default to ping.")
        print("    --nameserver=<server>  Use a specific nameserver for nslookup.")
        return

    # Input validation
    ip_input = sys.argv[1]
    options = sys.argv[2:]

    use_csv = False
    csv_filename = ""

    n_threads = 256

    custom_nameserver = ""
    for option in options:
        if option.startswith("--csv="):
            use_csv = True
            csv_filename = option.split("--csv=")[1]
    
        if option.startswith("--threads="):
            try:
                n_threads = int(option.split("--threads=")[1])
            except ValueError:
                print("nthreads must be an integer")
                return
            
            if n_threads < 1 or n_threads > 1024:
                print("nthreads must be in the range [1-1024]")
                return
        
        if option.startswith("--nameserver="):
            custom_nameserver = option.split("--nameserver=")[1]


    if len(ip_input.split("/")) != 2:
        print("Must include a subnet")
        return

    if len(ip_input.split(".")) != 4:
        print("Not in a valid ip address")
        return
    
    ip, subnet = ip_input.split("/")
    try:
        if int(subnet) < 16:
            print("Too broad a subnet. Must be >= 16")
            return
        
        if int(subnet) > 32:
            print("Not a valid subnet. Must be <= 32")
            return
    except ValueError:
        print("Not a valid subnet")
        return

    try:
        for sub_ip in ip.split("."):
            if int(sub_ip) < 0 or int(sub_ip) > 255:
                print("ip contains an invalid value")
                return
    except ValueError:
        print("Not a valid ip")
        return

    # Returns a list of ips inside the specified subnet
    ips = subnet_calculator(ip_input)

    # Final chance to abort
    print()
    if len(ips) > 1:
        print("Pinging range with {} thread{}:".format(n_threads, "s" if n_threads > 1 else ""))
        print("{} -> {}".format(ips[0], ips[-1]))
        print("Press enter to continue (ctrl+c to cancel)")
        try:
            input()
        except KeyboardInterrupt:
            print("Cancelling")
            return
    
    def ping(ip):
        """
        Worker function for each thread to perform. Run ping and nslookup.
        """
        print(f"Pinging {ip}")
        ping_text = os.popen(f"ping {ip}").read()
        nslookup_text = os.popen(f"nslookup {ip} {custom_nameserver}").read()

        pr = PingResult(ping_text).__dict__
        ns = NSLookupResult(nslookup_text).__dict__
        pr.update(ns)
        return pr

    results = []
    try:
        with ThreadPool(n_threads) as tp:
            results = tp.map(ping, ips)
    except KeyboardInterrupt:
        print()
        print("Killing threads")
        return
    
    df = pd.DataFrame.from_records(results)
    printable_df = df.drop(columns=["ping_result", "nslookup_result"])

    if use_csv:
        try:
            print("Writing csv...")
            with open(csv_filename, "w") as f:
                f.write(df.to_csv(lineterminator="\n"))
        except PermissionError:
            print(f"Cannot write to {csv_filename} at the moment. Using stdout.")
            print()
            print(printable_df.to_markdown())
    else:
        print(printable_df.to_markdown())


if __name__ == "__main__":
    main()
