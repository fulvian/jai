def foo(sub_query=None):
    pass


try:
    foo(**{'"sub_query"': "find"})
except Exception as e:
    print(f"ERROR: {type(e).__name__} = {str(e)}")
