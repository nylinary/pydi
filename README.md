# pydic
Simple Python DI container.

# Config setup

Config must be a python dictionary with key - string representation of dependency class/interface and value of `DIConf` class:

```python
from pydi.container import DIConf
from pydi.container import Container


# Just for example
class SomeClass:
    def run(self):
        print("Run SomeClass")

# Just for example
class AnotherClass:
    def run(self):
        print("Run AnotherClass")


DI_CONFIG = {
    "BaseNotifyer": DIConf(cls_=SomeClass),
    "TGNotifyer": DIConf(cls_=AnotherClass),
}

container = Container(DI_CONFIG)
```

# Usage
pydi `Container` works on *decorator pattern*. Use `contaner` variable from previous section and call `use_container` method as decorator.

If dependency's type string representation in `DI_CONFIG` keys - dependency will be automatically initialized and used.

```python
from my_settings import container


class MyClass:
    @container.use_container
    def my_super_method(self, some_dependency: SomeClass) -> None:
        some_dependency.run()
```

### Results
```sh
>>> Myclass().my_super_method()
>>> Run SomeClass
```

# DIConf
DIConf class is used to config dependency and its initialization options.

Parameters are:
1. ### cls_ `(Required)`

    Dependency class variable. 
    
    `Note:`
    
    it must be  class, not instance.

    `Example:`
    ```python
    DIConf(cls_=SomeClass)
    ```

2. ### args 
    Python list of argumets to pass in `*args` to dependency `__init__` method.
    
    `Example:`
    ```python
    DIConf(cls_=SomeClass, args=[True, 123.999,])
    ```

3. ### kwargs 
    Python dict of keyword argumets to pass in `**kwargs` to dependency `__init__` method.
    
    `Example:`
    ```python
    DIConf(cls_=SomeClass, kwargs={"param1": True, "param2": 123.999})
    ```

4. ### calls 
    Python list of `Call` instances, to perform **after** dependency initialization.

    `Note:`

    Details about `Call` class will be in the section below.
    
    `Example:`
    ```python
    DIConf(cls_=SomeClass, calls=[Call(method="post_init_config"), Call(method="set_locale", args=["EN"], kwargs={"country": "Canada"})])
    ```

5. ### attrs
    Python dict of instance attributes to set **after** dependency initialization.
        
    `Example:`
    ```python
    DIConf(cls_=SomeClass, attrs={"locale": "EN", "country": "Canada"})
    ```

6. ### cache
    Python bool, used to define either to cache instance or not.

    If set to True, dependency will be evaluated oonly once, and stored as internally.

    With any subsequent dependency call, cached instance will be returned.

    `Default is False` 
        
    `Example:`
    ```python
    DIConf(cls_=SomeClass, cache=True)
    ```


# Call
Call class is used to config dependecy's post initialization method call.

Parameters are:

1. ### method `(Required)`

    Method name as python string.

    `Example:`

    ```python
    DIConf(cls_=SomeClass, calls=[Call(method="post_init_config")])
    ``` 

2. ### args

    Python list of argumets to pass in `*args` to method.

    `Example:`
    ```python
    DIConf(cls_=SomeClass, calls=[Call(method="set_locale", args=["EN"])])
    ```

3. ### kwargs

    Python dict of keyword argumets to pass in `**kwargs` to method.

    `Example:`
    ```python
    DIConf(cls_=SomeClass, calls=[Call(method="set_locale", kwargs=["locale": "EN"])])
    ```


# Examples

## Dependencies can be resolved recursivelly. E.g.:

`connectors.py`
```python
from pydi.container import DIConf
from pydi.container import Container
from abc import ABC, abstractmethod


class AbstractSMTPConn(ABC):
    @abstractmethod
    def conn(self):
        ...


class OldSMTPConn(AbstractSMTPConn):
    def conn(self):
        print("Old SMTP connected!")


class NewSMTPConn(AbstractSMTPConn):
    def conn(self):
        print("New SMTP connected!")
```


`notifyers.py`
```python
class AbstractNotifyer(ABC):
    @abstractmethod
    def notify(self):
        ...

class EmailNotifyer(AbstractNotifyer):
    @container.use_container
    def __init__(self, conn: AbstractSMTPConn):
        self.conn = conn

    def notify(self):
        with self.conn as c:
            c.send("Some msg")
```

```python
DI_CONFIG = {
    "AbstractSMTPConn": DIConf(cls_=NewSMTPConn),
    "Notifyer": DIConf(cls_=EmailNotifyer),
}

container = Container(DI_CONFIG)


class Login:
    @container.use_container
    def login(self, notifyer: Notifyer):
        # some business logic ...
        notifyer.send("You have logged in")


Login().login()
```