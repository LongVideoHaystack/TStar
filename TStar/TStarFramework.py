
"""
TStarSearcher: Comprehensive Video Frame Search Tool

This script allows searching for specific objects within a video using YOLO object detection and GPT-4 for question-answering. It leverages the TStar framework's universal Grounder, YOLO interface, and video searcher to identify relevant frames and answer questions based on the detected objects.

Usage:
    python tstar_searcher.py --video_path path/to/video.mp4 --question "Your question here" --options "A) Option1\nB) Option2\nC) Option3\nD) Option4"
"""

import os
import sys
import cv2
import torch
import copy
import logging
import argparse
import numpy as np
import matplotlib.pyplot as plt
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from decord import VideoReader, cpu
from scipy.interpolate import UnivariateSpline

# Import custom TStar interfaces
from TStar.interface_llm import TStarUniversalGrounder
from TStar.interface_yolo import YoloWorldInterface, YoloInterface
from TStar.interface_searcher import TStarSearcher
from TStar.utilites import save_as_gif
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class TStarFramework:
    """
    Main class for performing object-based frame search and question-answering in a video.
    """

    def __init__(
        self,
        video_path: str,
        yolo_scorer: YoloInterface,
        grounder: TStarUniversalGrounder,
        question: str,
        options: str,
        search_nframes: int = 8,
        grid_rows: int = 4,
        grid_cols: int = 4,
        output_dir: str = './output',
        confidence_threshold: float = 0.6,
        search_budget: int = 1000,
        prefix: str = 'stitched_image',
        config_path: Optional[str] = None,
        checkpoint_path: Optional[str] = None,
        device: str = "cuda:0"
    ):
        """
        Initialize VideoSearcher.

        Args:
            video_path (str): Path to the input video file.
            yolo_scorer (YoloV5Interface): YOLO interface instance.
            grounder (TStarUniversalGrounder): Universal Grounder instance.
            question (str): The question for question-answering.
            options (str): Multiple-choice options for the question.
            search_nframes (int, optional): Number of top frames to return. Default is 8.
            grid_rows (int, optional): Number of rows in the image grid. Default is 4.
            grid_cols (int, optional): Number of columns in the image grid. Default is 4.
            output_dir (str, optional): Directory to save outputs. Default is './output'.
            confidence_threshold (float, optional): YOLO detection confidence threshold. Default is 0.6.
            search_budget (int, optional): Maximum number of frames to process during search. Default is 1000.
            prefix (str, optional): Prefix for output filenames. Default is 'stitched_image'.
            config_path (str, optional): Path to the YOLO configuration file. Default is None.
            checkpoint_path (str, optional): Path to the YOLO model checkpoint. Default is None.
            device (str, optional): Device for model inference (e.g., "cuda:0" or "cpu"). Default is "cuda:0".
        """
        self.video_path = video_path
        self.yolo_scorer = yolo_scorer
        self.grounder = grounder
        self.question = question
        self.options = options
        self.search_nframes = search_nframes
        self.grid_rows = grid_rows
        self.grid_cols = grid_cols
        self.output_dir = output_dir
        self.confidence_threshold = confidence_threshold
        self.search_budget = search_budget
        self.prefix = prefix
        self.config_path = config_path
        self.checkpoint_path = checkpoint_path
        self.device = device

        # Ensure the output directory exists
        os.makedirs(self.output_dir, exist_ok=True)
        logger.info("VideoSearcher initialized successfully.")

        self.results = {}

    def run(self):
        """
        Execute the complete video search and question-answering process.
        """
        # Use Grounder to get target and cue objects
        target_objects, cue_objects = self.get_grounded_objects()

        # Initialize TStarSearcher
        video_searcher = TStarSearcher(
            video_path=self.video_path,
            target_objects=target_objects,
            cue_objects=cue_objects,
            search_nframes=self.search_nframes,
            image_grid_shape=(self.grid_rows, self.grid_cols),
            output_dir=self.output_dir,
            confidence_threshold=self.confidence_threshold,
            search_budget=self.search_budget,
            prefix=self.prefix,
            yolo_scorer=self.yolo_scorer
        )
        
        logger.info(f"TStarSearcher initialized successfully for video {self.video_path}.")

        # Perform search
        all_frames, time_stamps = self.perform_search(video_searcher)

        # Save retrieved frames
        self.save_frames(all_frames, time_stamps)
        self.save_searching_iters(video_searcher)
        # Plot and save score distribution
        self.plot_and_save_scores(video_searcher)

        # Perform question-answering on retrieved frames
        answer = self.perform_qa(all_frames)
        print("QA Answer:", answer)

        logger.info("VideoSearcher completed successfully.")

    def get_grounded_objects(self) -> Tuple[List[str], List[str]]:
        """
        Use Grounder to obtain target and cue objects.

        Returns:
            Tuple[List[str], List[str]]: Lists of target objects and cue objects.
        """
        # Example code; should be implemented based on Grounder's interface
        # For example:
        target_objects, cue_objects = self.grounder.inference_query_grounding(
            video_path=self.video_path,
            question=self.question
        )
        # Here, assuming fixed target and cue objects
        # target_objects = ["couch"]  # Target objects to find
        # cue_objects = ["TV", "chair"]  # Cue objects

        logger.info(f"Target objects: {target_objects}")
        logger.info(f"Cue objects: {cue_objects}")
        self.results["Searching_Objects"] = {"target_objects": target_objects, "cue_objects": cue_objects}
        return target_objects, cue_objects

    def perform_search(self, video_searcher: TStarSearcher) -> Tuple[List[np.ndarray], List[float]]:
        """
        Execute the frame search process and retrieve relevant frames and timestamps.

        Args:
            video_searcher (TStarSearcher): Instance of TStarSearcher.

        Returns:
            Tuple[List[np.ndarray], List[float]]: List of frames and their corresponding timestamps.
        """
        all_frames, time_stamps = video_searcher.search_with_visualization()
        logger.info(f"Found {len(all_frames)} frames, timestamps: {time_stamps}")
        
        self.results['timestamps'] = time_stamps
        return all_frames, time_stamps

    def perform_qa(self, frames: List[np.ndarray]) -> str:
        """
        Perform question-answering on the retrieved frames.

        Args:
            frames (List[np.ndarray]): List of frames to analyze.

        Returns:
            str: Answer generated by VLM.
        """
        answer = self.grounder.inference_qa(
            frames=frames,
            question=self.question,
            options=self.options
        )
        self.results['answer'] = answer
        return answer

    def plot_and_save_scores(self, video_searcher: TStarSearcher):
        """
        Plot the score distribution and save the plot.

        Args:
            video_searcher (TStarSearcher): Instance of TStarSearcher.
        """
        plot_path = os.path.join(self.output_dir, "score_distribution.png")
        video_searcher.plot_score_distribution(save_path=plot_path)
        logger.info(f"Score distribution plot saved to {plot_path}")

    def save_frames(self, frames: List[np.ndarray], timestamps: List[float]):
        """
        Save the retrieved frames as image files.

        Args:
            frames (List[np.ndarray]): List of frames to save.
            timestamps (List[float]): Corresponding timestamps of the frames.
        """
        for idx, (frame, timestamp) in enumerate(zip(frames, timestamps)):
            frame_path = os.path.join(
                self.output_dir,
                f"frame_{idx}_at_{timestamp:.2f}s.jpg"
            )
            cv2.imwrite(frame_path, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
            logger.info(f"Saved frame to {frame_path}")

    def save_searching_iters(self, video_searcher, video_ids=[]):
        # # 定义 resize 操作，目标大小为 (640, 640)
        # resize_transform = T.Resize((1024, 1024))
        # resized_frames_tensor = resize_transform(resized_frames_tensor)
        
        image_grid_iters = video_searcher.image_grid_iters # iters, b, image # b = 1 for v1
        detect_annotot_iters = video_searcher.detect_annotot_iters # iters, b, image
        detect_bbox_iters = video_searcher.detect_bbox_iters #iters, b, n_objects, xxyy, 
            
        fps = 1  # 设置帧率为 2
        for b in range(len(image_grid_iters[0])):
            images =  [image_grid_iter[b] for image_grid_iter in image_grid_iters]
            anno_images = [detect_annotot_iter[b] for detect_annotot_iter in detect_annotot_iters] 

            frame_size = (anno_images[0].shape[1], anno_images[0].shape[0])  # 获取图像大小 (宽度, 高度)

            # 设置视频的参数
            video_id=self.video_path.split("/")[-1].split(".")[0]
            output_video_path = os.path.join(self.output_dir, f"{video_id}.gif")  # 视频保存路径
            save_as_gif(images=anno_images, output_gif_path=output_video_path)
            # fourcc = cv2.VideoWriter_fourcc(*'MJPG')  # 使用 'mp4v' 编码器
            # # 创建 VideoWriter 对象
            # video_writer = cv2.VideoWriter(output_video_path, fourcc, fps, frame_size)

            # # 将每一帧图像写入视频
            # for img in anno_images:
            #     # 确保图像是 uint8 类型
            #     frame = img.astype(np.uint8)
            #     # 写入当前帧
            #     video_writer.write(frame)

            # # 释放 VideoWriter
            # video_writer.release()
            # print("save video ")
            # pass
    


def initialize_yolo(
    config_path: str,
    checkpoint_path: str,
    device: str
) -> YoloInterface:
    """
    Initialize the YOLO object detection model.

    Args:
        config_path (str): Path to the YOLO configuration file.
        checkpoint_path (str): Path to the YOLO model checkpoint.
        device (str): Device for model inference (e.g., "cuda:0").

    Returns:
        YoloWorldInterface: Initialized YOLO interface instance.

    Raises:
        FileNotFoundError: If the configuration file or checkpoint file is not found.
    """

    yolo = YoloWorldInterface(
        config_path=config_path,
        checkpoint_path=checkpoint_path,
        device=device
    )
    logger.info("YoloWorldInterface initialized successfully.")
    return yolo


def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Returns:
        argparse.Namespace: Parsed arguments.
    """
    parser = argparse.ArgumentParser(description="TStarSearcher: Video Frame Search and QA Tool")
    parser.add_argument('--video_path', type=str, default="./38737402-19bd-4689-9e74-3af391b15feb.mp4", help='Path to the input video file.')
    parser.add_argument('--question', type=str, default="What is the color of my couch?", help='Question for video content QA.')
    parser.add_argument('--options', type=str, default="A) Red\nB) Black\nC) Green\nD) White\n", help='Multiple-choice options for the question, e.g., "A) Option1\nB) Option2\nC) Option3\nD) Option4"')
    parser.add_argument('--config_path', type=str, default="./YOLOWorld/configs/pretrain/yolo_world_v2_xl_vlpan_bn_2e-3_100e_4x8gpus_obj365v1_goldg_train_lvis_minival.py", help='Path to the YOLO configuration file.')
    parser.add_argument('--checkpoint_path', type=str, default="./pretrained/YOLO-World/yolo_world_v2_xl_obj365v1_goldg_cc3mlite_pretrain-5daf1395.pth", help='Path to the YOLO model checkpoint.')
    parser.add_argument('--device', type=str, default="cuda:0", help='Device for model inference (e.g., "cuda:0" or "cpu").')
    parser.add_argument('--search_nframes', type=int, default=8, help='Number of top frames to return.')
    parser.add_argument('--grid_rows', type=int, default=4, help='Number of rows in the image grid.')
    parser.add_argument('--grid_cols', type=int, default=4, help='Number of columns in the image grid.')
    parser.add_argument('--confidence_threshold', type=float, default=0.7, help='YOLO detection confidence threshold.')
    parser.add_argument('--search_budget', type=float, default=0.5, help='Maximum ratio of frames to process during search.')
    parser.add_argument('--output_dir', type=str, default='./output', help='Directory to save outputs.')
    parser.add_argument('--prefix', type=str, default='stitched_image', help='Prefix for output filenames.')
    return parser.parse_args()


def main():
    """
    Main function to execute TStarSearcher.
    """
    args = parse_arguments()

    # Initialize Grounder
    grounder = TStarUniversalGrounder(
        backend="gpt4",
        gpt4_model_name="gpt-4o"
    )
    logger.info("TStarUniversalGrounder initialized successfully.")

    # Initialize YOLO interface
    yolo_interface = initialize_yolo(
        config_path=args.config_path,
        checkpoint_path=args.checkpoint_path,
        device=args.device
    )

    # Initialize VideoSearcher
    searcher = TStarFramework(
        grounder=grounder,
        yolo_scorer=yolo_interface,
        video_path=args.video_path,
        question=args.question,
        options=args.options,
        search_nframes=args.search_nframes,
        grid_rows=args.grid_rows,
        grid_cols=args.grid_cols,
        output_dir=args.output_dir,
        confidence_threshold=args.confidence_threshold,
        search_budget=args.search_budget,
        prefix=args.prefix,
        device=args.device
    )

    # Run the search and QA process
    searcher.run()

    # Output the results
    print("Final Results:")
    print(f"Grounding Objects: {searcher.results['Searching_Objects']}")
    print(f"Frame Timestamps: {searcher.results['timestamps']}")
    print(f"Answer: {searcher.results['answer']}")


    


if __name__ == "__main__":
    main()
