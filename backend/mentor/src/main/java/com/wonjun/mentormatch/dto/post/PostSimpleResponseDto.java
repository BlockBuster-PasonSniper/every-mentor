package com.wonjun.mentormatch.dto.post;

import com.wonjun.mentormatch.domain.post.Post;
import com.wonjun.mentormatch.domain.post.PostStatus;
import lombok.Getter;

import java.time.LocalDateTime;

@Getter
public class PostSimpleResponseDto {
    private final Long id;
    private final String title;
    private final String category;
    private final PostStatus status;
    private final String mentorName;
    private final LocalDateTime createdAt;

    public PostSimpleResponseDto(Post entity) {
        this.id = entity.getId();
        this.title = entity.getTitle();
        this.category = entity.getCategory();
        this.status = entity.getStatus();
        this.mentorName = entity.getMember().getName();
        this.createdAt = entity.getCreatedAt();
    }
}
