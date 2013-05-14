f = open("scriptCases.txt")

tokens = [line.strip().split(" ") for line in f]
tokens = [tokenline for tokenline in tokens if tokenline[0] != "//"]
tests = zip(*((iter(tokens),)*2))
tests = [(test[0],test[1][0]) for test in tests]
