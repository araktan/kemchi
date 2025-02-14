# kemchi liquid handling #
A project for liquid handling automation, screening and for handling any repetitive "wet chemistry". 

The basic usage is automating experimental chemistry procedures via high level commands similar to this:

```python
move_liquid(from='source', to='destination', volume_ml=10)
```


## usage ##

Recommended usage is via jupyterlab notebooks. This way every step of the procedure can be tested by testing hardware, swapping chemical solutions and testing sections of the chemical procedures in separate notebook cells. This allows to iterate quickly and interactively, plus - no one wants to degbug in the middle of running a reaction

Actual usage starts with setting up the liquid handling module
```python
import kemchi

k0 = kemchi.DaisyChain('config_files/port_map.yaml','config_files/config.yaml') ##

k0.initialize_daisy_chain()
```

The basic liquid move command is then for example:
```python
k0.move_liquid('toluene', 'reactor1', volume=10)
```
this would add 10ml of toluene to reactor1.


## liquid handling backbone topology ##

The backbone is aranged daisy-chain topology - single pump, with additional linearly conmnected distribution valves. The key takeaway is that it drastically increases efficiency of hardware, decreases dead volumes, increases number of productive ports as well as permits minimalistic and intuitive codebase.

The code started as a script to control some kloehn pumps and valves via python (pySerial). It grew substantially but remains lighweight and minimalistic. The goal is to keep it light, modular and convenient for direct labwork in test-modify-iterate workflow stage and leave for subsequent unantended automated labwork on expanded scope or repeated experimentation.

- current goal: add a firstime use walktrough and examples
- next: start the refactoring for conventional packaging

Meanwhile let me know of any comments or suggestions.
