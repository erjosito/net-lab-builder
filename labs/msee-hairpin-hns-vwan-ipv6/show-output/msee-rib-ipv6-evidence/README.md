# MSEE (ExpressRoute circuit) route table - AzurePrivatePeering
# Captured 2026-06-16T10:13:48.8985595+02:00
# Question: which IPv6 routes does the ER circuit learn from vWAN?
# Answer: NONE. Only HnS-originated IPv6 (fd00:1::/48, fd00:2::/48) is present.
# vWAN ER GW injects IPv4 (10.3.0.0/23, 10.4.0.0/24) but zero IPv6.

