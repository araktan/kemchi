
# WARNING: UNTESTED
# TODO: test example funcs and potential inheritance bugs, check the utility of a new class vs external func

from kemchi import DaisyChain
import time

class BatchDaisy(DaisyChain):
    # TODO: custom function, to be move out to examples
    def load_chemicals_to_reactors(self, exp_subset, reactors, STEP):
        for chemical_name_step in STEP:
            if np.any(exp_subset[chemical_name_step]):
                chemical_name = chemical_name_step.split('_')[0]
                # PRIME CHEMICAL
                #print(f'priming {chemical_name}')
                self.move_liquid(chemical_name, 'waste', 0.5, 4)
                chemical_stock = list(exp_subset[chemical_name_step])
                for reactor_index, volume in enumerate(chemical_stock):
                    if volume != 0:
                        #print(f'moving {volume} ml from {chemical_name} to {reactors[reactor_index]}')
                        self.move_liquid(chemical_name, reactors[reactor_index], volume)
        return

    # TODO: custom function, to be move out to examples
    def sample_reactors(self, reactors, count):
        for i in range(count):
            self.move_liquid(reactors[i], 'waste', 0.5, 2) # TODO: needs to account for the dead volume of tube
            self.move_liquid(reactors[i], 'sampler', 1)
            self.move_liquid('air', 'waste', 2)
            self.move_liquid('air', 'sampler', 1)
            self.move_liquid('water', 'waste', 2)
            self.move_liquid('water', 'sampler', 0.5)
            self.move_liquid('air', 'waste', 2)
            self.move_liquid('air', 'sampler', 1)
            self.sampler_next()
            time.sleep(1)
        return

    # TODO: created as a custom function, to be move out to examples
    def check_chem_ports(self, df, exclude_list):
        ports = self.port_map.keys()
        chems_steps = df.columns
        for chem_step in chems_steps:
            chem = chem_step.split('_')[0]
            if chem not in ports and chem not in exclude_list:
                raise Exception(f'Chemical {chem} not added to port_map.yaml configuration file!')
            elif chem not in exclude_list:
                print(f'{chem_step}: {chem}: {port_map[chem]} OK')
        print('Chem port check result: appears ok')
        return