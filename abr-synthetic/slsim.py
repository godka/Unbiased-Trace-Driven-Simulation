import numpy as np
import torch
import torch.nn as nn
from torch.utils.tensorboard import SummaryWriter
import os
from tqdm import tqdm
from sklearn.model_selection import train_test_split
from nn_util import MLP


def train_slsim(
    datapath,
    models_path="models",
    BATCH_SIZE=2**13,
    N=int(5 * 1e6),
):
    path_models = f"{models_path}/slsim/"

    try:
        os.makedirs(path_models)
    except:
        pass
    log_path = f"{path_models}/logs"
    try:
        os.makedirs(log_path)
    except:
        pass

    if torch.cuda.is_available():
        device = torch.device(f"cuda:1")
    else:
        device = torch.device(f"cpu")

    inputs_train = np.load(f"{datapath}/white_train_inputs_synthetic.npy")  #
    # [:, (buffer, chosen_chunk_size,   min_rtt, c_hat)]

    outputs_train = np.load(f"{datapath}/white_train_outputs_synthetic.npy")[:, :]
    # [:, (next_buffer, download_time, policy_label)]

    val_size = int(inputs_train.shape[0] * 0.15)
    train_idx, val_idx = train_test_split(
        np.arange(len(inputs_train)), test_size=val_size, train_size=None
    )

    train_input_tensors = torch.as_tensor(
        inputs_train[train_idx], dtype=torch.float32, device=device
    )
    train_output_tensors = torch.as_tensor(
        outputs_train[train_idx], dtype=torch.float32, device=device
    )

    val_input_tensors = torch.as_tensor(
        inputs_train[val_idx], dtype=torch.float32, device=device
    )
    val_output_tensors = torch.as_tensor(
        outputs_train[val_idx], dtype=torch.float32, device=device
    )

    buffer_predictor = MLP(
        input_dim=4, output_dim=2, hidden_sizes=[128, 128], activation=nn.ReLU
    ).to(device)

    mse_loss = nn.MSELoss()
    buffer_predictor_optimizer = torch.optim.Adam(
        buffer_predictor.parameters(), lr=1e-4
    )
    writer_train = SummaryWriter(log_dir=f"{log_path}")
    best_loss = np.inf
    for epoch in tqdm(range(20000)):
        # Predictor training:
        idx = np.random.choice(np.arange(len(train_input_tensors)), size=BATCH_SIZE)
        batch_input_tensors = train_input_tensors[idx]
        batch_output_tensors = train_output_tensors[idx]
        buffer_predictor_optimizer.zero_grad()
        pred_tensors = buffer_predictor(batch_input_tensors[:, :])
        pred_loss = mse_loss(pred_tensors, batch_output_tensors[:, :2])
        writer_train.add_scalar(
            "predictor_loss/prediction", pred_loss.cpu().detach().numpy(), epoch
        )
        pred_loss.backward()
        buffer_predictor_optimizer.step()

        if epoch % 100 == 99:
            print(
                f"Train loss: epoch {epoch}, prediction loss {pred_loss.cpu().detach().numpy()}"
            )
            ## val loss
            pred_tensors = buffer_predictor(val_input_tensors[:, :])
            pred_loss = mse_loss(pred_tensors, val_output_tensors[:, :2])
            total_loss = pred_loss.cpu().detach().numpy()
            print(
                f"Val loss: epoch {epoch}, prediction loss {pred_loss.cpu().detach().numpy()}"
            )
            if best_loss > total_loss:
                best_loss = total_loss
                print(f"saving ... best losses: {best_loss},")
                torch.save(
                    buffer_predictor, f"{path_models}/best_buffer_" "predictor.pth"
                )
