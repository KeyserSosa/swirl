import swirl

@swirl.asynchronous
def first(a):
    print "> running first"
    foo = yield second(a)
    print "first got result: ", foo
    print "> done first"


@swirl.async_return
def second(a):
    print "running second"
    yield swirl.return_(square(a))
    print "this line should never be executed (second)"


@swirl.async_return
def square(a):
    print "running square"
    yield swirl.return_(a ** 2)
    print "this line should never be executed (square)"

@swirl.asynchronous
def test_loop(n):
    for i in range(n):
        x = yield square(i)
        print x
