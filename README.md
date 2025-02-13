### kemchi liquid handling ###
A project for liquid handling automation, screening and repetitive "wet chemistry". 

The basic usage is automating experimental chemistry procedures via high level commands such as this:

```python
move_liquid(from_source, to_destination, volume_ml)
```

The code started as a script to control some kloehn pumps and valves via python (pySerial). It grew substantially but still is really lighweight and minimalistic. I would like to keep it that way but it needs substantial refactoring to keep some more experienced eyes from twitching.
The reason this is public at this state is that I personally would have found this useful as a starting point when getting into lab automation.

- current goal: add a firstime use walktrough and examples
- next: start the refactoring for conventional packaging

Meanwhile let me know of any comments or suggestions.
