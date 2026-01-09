package com.wonjun.mentormatch.dto.post;

import com.wonjun.mentormatch.domain.Member;
import com.wonjun.mentormatch.domain.post.Post;
import com.wonjun.mentormatch.domain.post.PostStatus;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@NoArgsConstructor
public class PostSaveRequestDto {
    private String title;
    private String content;
    private String category;

    public Post toEntity(Member member) {
        return Post.builder()
                .member(member)
                .title(title)
                .content(content)
                .category(category)
                .status(PostStatus.OPEN) // Default status for new posts
                .build();
    }
}
