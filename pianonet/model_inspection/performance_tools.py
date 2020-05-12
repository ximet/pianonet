import copy
import math
import random
import time
from collections import deque

import numpy as np
from keras import backend as K


def get_performance(model, seed_note_array, num_time_steps):
    """
    Takes in a seed note array and generated num_timesteps of piano notes sampled
    from the model's output probabilities. A full NoteArray instance, including
    the seed note array data, is returned.

    seed_note_array: Seed data for model input. If None, silence is used as the seed. NOTE! This note array is
                     assumed to have its keys properly aligned. That is, indices 0, num_keys, 2*num_keys, ...etc.
                     are at the starts of new time steps, and a full key state is between 0 and num keys, for
                     instance.
    model: The Keras trained model for generating the probabilities of new notes
    num_time_steps: How many new time steps of notes to generate using the model
    """

    num_keys = seed_note_array.note_array_transformer.num_keys

    num_notes_in_model_input = model.get_input_shape_at(0)[1]

    input_placeholder = model.input
    output_placeholders = [layer.output for layer in model.layers]
    functor = K.function([input_placeholder, K.learning_phase()], output_placeholders)

    input_data = seed_note_array.get_values_in_range(start_index=-num_notes_in_model_input,
                                                     end_index=None,
                                                     use_zero_padding_for_out_of_bounds=False)  # SEE IF CAN BE TRUE

    layer_outputs = functor([np.array([input_data]), 1])

    def get_initial_state_at(layer_index, num_states):
        """
        Get the num_states outputs from layer layer_index.
        """

        intermediate_output = layer_outputs[layer_index]
        return [np.transpose([state]) for state in intermediate_output[0][-num_states - 1:-1]]

    print("Initializing state queues.")

    initial_state_queues = []

    for i in range(0, len(model.layers) - 3):
        layer = model.layers[i]

        if (layer.name.find('conv1d') != -1) and (i > 2):
            initial_state_queues.append(
                deque(get_initial_state_at(layer_index=(i - 1), num_states=layer.dilation_rate[0])))
        else:
            initial_state_queues.append(None)

    print("Resetting the state queues to the initial state (for a new performance).\n")
    state_queues = copy.deepcopy(initial_state_queues)  # Only run when starting a new performance
    output_data = seed_note_array.array.copy().tolist()

    raw_input = deque(copy.deepcopy(output_data)[-num_notes_in_model_input:])
    input_end_index = len(raw_input) - 1

    # This assumes a kernel size of two
    w_at_two = np.transpose(model.get_layer(index=2).get_weights()[0])
    b_at_two = np.transpose([model.get_layer(index=2).get_weights()[1]])

    saved_weight_entries = []
    for i in range(0, len(model.layers) - 3):
        node = model.layers[i]

        if node.name.find('conv1d') != -1:
            weights = node.get_weights()
            w = weights[0]
            b = np.transpose([weights[1]])

            w1 = np.transpose(w[0])
            w2 = np.transpose(w[1])

            saved_weight_entries.append({
                'w1': w1,
                'w2': w2,
                'b': b,
            }
            )
        else:
            saved_weight_entries.append({})

    def get_output_tensor_at_node(input_position, layer_index):
        """
        Recursively called function for building output states. Each node in the model is defined by an x coordinate,
        the input position, and a y coordinate, a layer index.
        """

        def sigmoid(x):
            return 1.0 / (1.0 + math.exp(-x))

        node = model.get_layer(index=layer_index)
        dilation_rate = node.dilation_rate[0]

        if layer_index == 2:
            w = w_at_two
            b = b_at_two

            inputs = np.transpose([raw_input[input_position - 1], raw_input[input_position]])

            result = np.matmul(w, inputs) + b

            result = result.clip(min=0)

            return result

        elif layer_index == (len(model.layers) - 3):  # last conv_1d with sigmoid
            final_layer = model.layers[layer_index]
            final_weights = final_layer.get_weights()
            w = final_weights[0][0]
            b = final_weights[1]
            inputs = np.transpose(get_output_tensor_at_node(input_position=input_position, layer_index=layer_index - 2))

            final_result = np.matmul(inputs, w) + np.transpose(np.array([[b]]))

            final_result = sigmoid(final_result)

            return final_result

        else:
            right_input = get_output_tensor_at_node(input_position=input_position, layer_index=(layer_index - 2))

            if input_position == input_end_index:
                state_queue = state_queues[layer_index]

                if len(state_queue) == dilation_rate:
                    left_input = state_queue.popleft()
                else:
                    raise Exception("State queue length should always be equal to dilation rate.")

                state_queue.append(right_input)
            else:
                raise Exception("Should never touch here.")

            w1 = saved_weight_entries[layer_index]['w1']
            w2 = saved_weight_entries[layer_index]['w2']
            b = saved_weight_entries[layer_index]['b']

            result = np.matmul(w1, left_input) + np.matmul(w2, right_input) + b

            result = result.clip(min=0)

            return result

    start = time.time()

    seconds = 0
    for time_step in range(0, num_time_steps):
        if time_step % 48 == 0:
            seconds += 1
            print("==> Time step " + str(time_step) + " seconds of audio is " + str(seconds))
        for key in range(0, num_keys):

            #             if key % 16 == 0:
            #                 print("\t", key)

            #             res_model = model.predict([[raw_input]])[0][-1]
            res = get_output_tensor_at_node(input_position=input_end_index, layer_index=(len(model.layers) - 3))

            #             print("\n\nFinal result: ", res)

            #             print("\nModel prediction:", res_model)

            pred = res > random.uniform(0.0, 1.0)
            output_data.append(pred)

            raw_input.popleft()
            raw_input.append(pred)

        end = time.time()

    print("\nTime per second of audio:", round((end - start) / (num_time_steps/48), 3), "seconds")

    # In[81]:

    # cleaned_final_pianoroll = np.array(output_data[0:-(len(output_data) % 64)])
    outputs_added = len(output_data) - seed_note_array.get_length_in_notes()

    print("Timesteps added:", outputs_added / num_keys)

    final_output_note_array = seed_note_array.note_array_transformer.get_note_array(flat_array=np.array(output_data))

    return final_output_note_array