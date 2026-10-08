/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import type { Meta, StoryObj } from "@storybook/react";
import { expect, userEvent, within } from "@storybook/test";
import { ImagePreview } from "./image-preview";

const meta = {
  title: "Image preview",
  component: ImagePreview,
  args: {
    onClose: () => undefined,
    images: [
      { id: "zhaoyun", name: "Zhao Yun.png", src: "https://game.gtimg.cn/images/yxzj/img201606/heroimg/107/107.jpg" },
      { id: "mengtian", name: "Meng Tian.png", src: "https://game.gtimg.cn/images/yxzj/img201606/heroimg/527/527.jpg" },
    ],
    initialId: "zhaoyun",
  },
  render: function Preview(args) {
    const [open, setOpen] = useState(false);
    return (
      <>
        <button type="button" onClick={() => setOpen(true)}>
          Open preview
        </button>
        {open && <ImagePreview {...args} onClose={() => setOpen(false)} />}
      </>
    );
  },
} satisfies Meta<typeof ImagePreview>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Gallery: Story = {
  play: async ({ canvasElement }) => {
    const page = within(canvasElement.ownerDocument.body);
    await userEvent.click(within(canvasElement).getByRole("button", { name: "Open preview" }));
    await expect(page.getByRole("button", { name: "Previous image" })).toBeDisabled();
    await userEvent.click(page.getByRole("button", { name: "Next image" }));
    await expect(page.getByRole("heading", { name: "Meng Tian.png" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Next image" })).toBeDisabled();
    await userEvent.keyboard("{Escape}");
    await expect(page.queryByRole("dialog")).not.toBeInTheDocument();
    await expect(within(canvasElement).getByRole("button", { name: "Open preview" })).toHaveFocus();
  },
};
